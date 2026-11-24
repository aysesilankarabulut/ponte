"""Ponte'nin uçtan uca akışı: rapor metni → okuma → açıklama → doktor soruları.

Komut satırındaki deney betiklerinin (read_hybrid.py, explain.py, doctor_questions.py)
yaptığı işi tek bir rapor için, fonksiyon olarak yapar. Web arayüzü (app.py) bunu kullanır.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import doctor_questions as dq
import explain as ex
import read_hybrid as rh
from parse_rules import canonical_units
from read_llm import candidate_lines
from verify import check_question, check_sentence, verify

TESTS = pd.read_csv("data/tests.csv")
NAMES = pd.read_csv("data/names_tr.csv").set_index("loinc").to_dict("index")
UNITS = canonical_units()
LANG_NAMES_TR = dq.LANG_NAMES_TR


def detect_lang(text):
    """Raporun dilini, içinde geçen tahlil adlarına bakarak tahmin eder."""
    low = text.lower()
    score = {lang: sum(1 for n in TESTS[f"name_{lang}"] if str(n).lower() in low)
             for lang in ["it", "de", "en", "es"]}
    return max(score, key=score.get)


UNIT_TESTS = {}
for _code, _unit in UNITS.items():
    UNIT_TESTS.setdefault(_unit, []).append(_code)


def direct_code(line):
    """Satırdaki birim yalnızca TEK bir tahlile aitse (ör. fL → MCV), o tahlilin kodu; değilse None."""
    found = [u for u in UNIT_TESTS if rh.find_unit(line, u) >= 0]
    if len(found) == 1 and len(UNIT_TESTS[found[0]]) == 1:
        return UNIT_TESTS[found[0]][0]
    return None


def read_report(text, model, direct=False):
    """Rapordaki tahlil satırlarını okur. Okunan satırları ve okunamayan satırları döndürür.
    direct=True: birimi tek bir tahlile ait olan satırları modele sormadan kod atar (daha hızlı)."""
    lines = candidate_lines(text)
    pairs = []                                        # (satır no, kod)
    ask = list(range(1, len(lines) + 1))
    if direct:
        for i in list(ask):
            code = direct_code(lines[i - 1])
            if code:
                pairs.append({"n": i, "code": code})
                ask.remove(i)
    start = time.time()
    raw = ""
    if ask:
        prompt = rh.numbered([lines[i - 1] for i in ask])
        raw = rh.ask_model(model, rh.build_instructions(TESTS), prompt, rh.answer_schema(UNITS.keys()))
        try:
            for x in json.loads(raw)["lines"]:
                k = int(x["n"])
                if 1 <= k <= len(ask):
                    pairs.append({"n": ask[k - 1], "code": str(x.get("code"))})   # asıl satır numarası
        except (ValueError, KeyError, TypeError):
            pass
    seconds = time.time() - start
    merged = json.dumps({"lines": pairs})
    rows = rh.rows_from_answer(merged, text, UNITS)
    used = {x["n"] for x in pairs if x["code"] in UNITS}
    # okunamayan satırlar: bilinen bir birim içeren ama hiçbir tahlile bağlanamayan satırlar
    unread = [line.strip() for i, line in enumerate(lines, 1)
              if i not in used and any(rh.find_unit(line, u) >= 0 for u in UNIT_TESTS)]
    return {"rows": rows, "unread": unread, "raw": raw, "seconds": seconds,
            "asked": len(ask), "direct": len(lines) - len(ask)}


def explain_rows(rows, model, chunks=1):
    """Okunan satırları sade Türkçeyle açıklar; her cümle doğrulamadan geçer.
    chunks>1: normal dışı sonuçlar parçalara bölünüp modele aynı anda gönderilir
    (Ollama birden fazla isteği paralel işleyebiliyorsa daha hızlı)."""
    facts = ex.build_facts(rows, NAMES)
    abnormal = [c for c, f in facts.items() if f["flag"] != "N"]
    start = time.time()
    groups = [abnormal[i::chunks] for i in range(chunks)] if abnormal else []
    groups = [g for g in groups if g]

    def ask(group):
        raw = ex.ask_model(model, {c: facts[c] for c in group})
        try:
            return json.loads(raw)["sentences"]
        except (ValueError, KeyError, TypeError):
            return []

    sentences = []
    if groups:
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            for part in pool.map(ask, groups):
                sentences += part
    accepted, rejected, added = verify(sentences, facts)
    # cümleleri rapordaki tahlil sırasına koy
    order = {c: i for i, c in enumerate(facts)}
    accepted.sort(key=lambda s: order.get(s["fact"], 999))
    return {"facts": facts, "accepted": accepted, "rejected": rejected, "added": added,
            "markdown": ex.render(facts, accepted, added), "seconds": time.time() - start}


OBJECT_RE = re.compile(r"\{[^{}]*\}")


def explain_stream(rows, model):
    """Açıklamayı model yazdıkça verir. Her tamamlanan cümle hemen doğrulanır.
    Üretir: ("cümle", {fact, text, problem}) ... ve en sonda ("bitti", sonuç)."""
    facts = ex.build_facts(rows, NAMES)
    start = time.time()
    text, seen, sentences = "", 0, []
    if any(f["flag"] != "N" for f in facts.values()):
        for piece in ex.stream_model(model, facts):
            text += piece
            body = text[text.find("["):] if "[" in text else ""
            found = OBJECT_RE.findall(body)
            for obj in found[seen:]:
                try:
                    s = json.loads(obj)
                except ValueError:
                    continue
                if "fact" in s and "text" in s:
                    sentences.append(s)
                    yield "cümle", {**s, "problem": check_sentence(s, facts)}
            seen = len(found)
    accepted, rejected, added = verify(sentences, facts)
    order = {c: i for i, c in enumerate(facts)}
    accepted.sort(key=lambda s: order.get(s["fact"], 999))
    yield "bitti", {"facts": facts, "accepted": accepted, "rejected": rejected, "added": added,
                    "markdown": ex.render(facts, accepted, added), "seconds": time.time() - start}


def doctor_questions(facts, lang, model):
    """Hastanın doktoruna sorabileceği soruları Türkçe ve rapor dilinde hazırlar."""
    doc_names = dict(zip(TESTS.loinc, TESTS[f"name_{lang}"]))
    codes = dq.top_abnormal(facts)
    start = time.time()
    proposed, rejected = [], []
    if codes:
        raw = dq.ask_model(model, facts, codes, lang, doc_names)
        try:
            proposed = json.loads(raw)["questions"][:2 * len(codes)]
        except (ValueError, KeyError, TypeError):
            proposed = []
    accepted = []
    for q in proposed:
        problem = check_question(q, facts, lang)
        if problem:
            rejected.append({**q, "problem": problem})
        elif q["fact"] in codes:
            accepted.append(q)
    final = dq.compose(accepted, facts, codes, lang, doc_names)
    return {"final": final, "rejected": rejected, "seconds": time.time() - start}


def results_table(facts):
    """Arayüzde gösterilecek sonuç tablosu."""
    rows = []
    for code, f in facts.items():
        rows.append({"Tahlil": f["name"],
                     "Değer": ex.fmt(f["value"]),
                     "Birim": f["unit"],
                     "Referans aralığı": f["range"],
                     "Durum": f["level"] or "normal"})
    order = {"yüksek": 0, "düşük": 0, "sınırda yüksek": 1, "sınırda düşük": 1, "normal": 2}
    return pd.DataFrame(rows).sort_values("Durum", key=lambda s: s.map(order), kind="stable")


def warm_up(model):
    """Modeli belleğe önceden yükler (ilk istekteki bekleme süresini azaltır)."""
    import urllib.request
    body = json.dumps({"model": model, "messages": [], "keep_alive": "30m"}).encode("utf-8")
    req = urllib.request.Request(rh.OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=300).read()
    except Exception:
        pass
