"""Karma okuyucu: dil modeli ADI tanır, kod SAYILARI okur.

İş bölümü:
  - Dil modeli: numaralı her satır için tek bir şey söyler, hangi tahlil (LOINC) ya da NONE.
    Kısaltma, OCR hatası, dört dil... bunlar modelin güçlü olduğu yer.
  - Kod: o satırda birimi bulur; birimden önceki sayı değer, sonraki kısım referans aralığıdır.
    "< 200", "fino a 200", "> 40" gibi tek sınırlı aralıkları da kod çözer.
    Sayılarda model hata yapamaz, çünkü sayılara hiç dokunmuyor.

Kullanım:
  python src/read_hybrid.py                 → llama3.2:3b, dil başına 5 rapor
  python src/read_hybrid.py --model gemma3:4b
"""
import argparse
import difflib
import json
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from generate_report import LANGS
from parse_rules import canonical_units, flag, normalize_unit, to_float
from read_llm import OLLAMA_URL, candidate_lines

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Tek sınırlı aralıkları anlatan kelimeler (dört dilde)
UPPER_WORDS = ["<", "fino a", "bis", "up to", "hasta", "max"]
LOWER_WORDS = [">", "superiore a", "über", "above", "superior a", "min"]


def build_instructions(tests):
    """Bilinen test listesi KARIŞIK sırayla verilir: raporlardaki sırayla aynı olursa model
    satırları okumadan listeyi sırayla kopyalayarak 'doğru' cevap verebilir (kısa yol)."""
    rows = [(t.loinc, t.name_en) for _, t in tests.iterrows()]
    random.Random(7).shuffle(rows)
    known = "\n".join(f"{code} = {name}" for code, name in rows)
    return f"""You classify the lines of a laboratory report.
The report may be in Italian, German, English or Spanish. Test names may be abbreviated
(e.g. Hb, GPT), upper case, or contain OCR typos (0 instead of o, 1 instead of l).

Known tests (LOINC code = English name):
{known}

Each input line starts with a number. For EVERY input line give the LOINC code of the test
on that line, or NONE if the line is not a test result (patient data, dates, page numbers).
Answer in JSON.

Example input:
1: Patient: John Doe  Date of birth: 01/02/1970
2: HEMOGLOBIN   Result: 10.2   g/dL    Normal: 12.0-16.0
3: Total chol.  269.8 mg/dL   max 200
Example output:
{{"lines": [{{"n": 1, "code": "NONE"}}, {{"n": 2, "code": "718-7"}}, {{"n": 3, "code": "2093-3"}}]}}"""


def answer_schema(codes):
    """Ollama'ya verilen JSON şeması. Model bu kalıbın dışına çıkamaz ve 'code' alanına
    yalnızca listedeki kodlardan birini ya da NONE yazabilir (kısıtlı üretim)."""
    return {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"n": {"type": "integer"},
                           "code": {"type": "string", "enum": sorted(codes) + ["NONE"]}},
            "required": ["n", "code"]}}},
        "required": ["lines"],
    }


def ask_model(model, instructions, text, schema):
    """Ollama'ya numaralı satırları gönderir; cevabın JSON şemasına uymasını zorunlu kılar."""
    body = {
        "model": model,
        "stream": False, "keep_alive": "30m",
        "format": schema,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Lines:\n{text}"},
        ],
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read())["message"]["content"]


def _key(text):
    """Büyük/küçük harf ve µ/u farkını yok sayan karşılaştırma anahtarı (uzunluğu değiştirmez)."""
    return text.lower().replace("µ", "u").replace("μ", "u")


def find_unit(line, unit):
    """Birimin satırdaki yerini bulur; bulamazsa -1. Birimi TAM kelime olarak arar:
    'g/dL' aranırken 'mg/dL' ya da 'µg/dL' içindeki 'g/dL' parçası sayılmaz."""
    pattern = r"(?<![\w/^])" + re.escape(_key(unit)) + r"(?![\w/])"
    matches = list(re.finditer(pattern, _key(line)))
    return matches[-1].start() if matches else -1


def parse_line(line, unit):
    """Bir satırdan değeri ve aralığı çıkarır. Bulamazsa None döndürür.
    Yöntem: satırda birimi bul → önceki son sayı değer, sonrası aralık."""
    pos = find_unit(line, unit)
    if pos < 0:
        return None
    before, after = line[:pos], line[pos + len(unit):]
    numbers = NUMBER_RE.findall(before)
    if not numbers:
        return None
    value = to_float(numbers[-1])
    found = [to_float(n) for n in NUMBER_RE.findall(after)]
    after_key = _key(after)
    if len(found) >= 2:
        low, high = found[0], found[1]
    elif len(found) == 1 and any(w in after_key for w in UPPER_WORDS):
        low, high = None, found[0]
    elif len(found) == 1 and any(w in after_key for w in LOWER_WORDS):
        low, high = found[0], None
    else:
        low = high = None                       # aralık okunamadı
    raw_unit = line[pos:pos + len(unit)]
    return value, normalize_unit(raw_unit, unit), low, high


def numbered(lines):
    return "\n".join(f"{i}: {line.strip()}" for i, line in enumerate(lines, 1))


_NAMES = None


def _test_names():
    """Her tahlilin dört dildeki adları (birim onarımında ad benzerliği için)."""
    global _NAMES
    if _NAMES is None:
        t = pd.read_csv("data/tests.csv")
        _NAMES = {r.loinc: [_key(str(getattr(r, f"name_{l}"))) for l in LANGS] for r in t.itertuples()}
    return _NAMES


def line_label(line):
    """Satırın ilk değerden önceki kısmı (tahlil adı); 'Co1esterol' içindeki 1 bölmesin."""
    m = re.match(r"^(.*?)[\s:.]+[<>]?\s*\d", line)
    return _key(m.group(1) if m else line)


def name_similarity(label, code):
    """Satırdaki ad ile tahlilin dört dildeki adlarından en benzeyeni arasındaki benzerlik (0–1)."""
    return max((difflib.SequenceMatcher(None, label, n).ratio() for n in _test_names().get(code, [])),
               default=0.0)


def repair_code(line, units):
    """Birim onarımı: modelin seçtiği tahlilin birimi satırda yoksa (ör. 'Hemoglobina glicada … %'
    satırına hemoglobin demişse), satırdaki birime uyan tahliller arasından ADI en çok benzeyeni seçer."""
    candidates = [c for c, u in units.items() if find_unit(line, u) >= 0]
    if len(candidates) == 1:
        return candidates[0]
    label = line_label(line)
    best = max(candidates, key=lambda c: name_similarity(label, c), default=None)
    return best if best and name_similarity(label, best) >= 0.5 else None


def name_check(line, code, units):
    """Ad tutarlılığı: model birimi tutan ama ADI tutmayan bir tahlil seçtiyse (ör. 'Harnsäure'
    satırına kalsiyum), aynı birimdeki tahliller arasında adı çok daha iyi uyan varsa onu seçer."""
    label = line_label(line)
    current = name_similarity(label, code)
    others = [c for c, u in units.items() if c != code and find_unit(line, u) >= 0]
    best = max(others, key=lambda c: name_similarity(label, c), default=None)
    if best and name_similarity(label, best) >= 0.85 and name_similarity(label, best) - current >= 0.2:
        return best
    return code


def rows_from_answer(raw, report, units, repair=True):
    """Modelin 'numara|LOINC' cevabını ve rapor metnini birleştirip tabloyu kurar.
    repair=True: iki kontrol yapılır.
      - Ad tutarlılığı: model birimi tutan ama adı tutmayan bir tahlil seçtiyse düzeltilir.
      - Birim onarımı: birimi tutmayan ya da boş bırakılan satırlara, birimi ve adı uyan tahlil atanır.
    repair=False: modelin cevabı olduğu gibi kullanılır (önceki deneylerle karşılaştırma için)."""
    lines = candidate_lines(report)
    try:                                              # yeni biçim: JSON
        answer = json.loads(raw)
        # "direct": modele sormadan kodun kendisinin atadığı satırlar (daraltmalı biçim)
        pairs = [(int(x["n"]), str(x["code"])) for x in answer["lines"] + answer.get("direct", [])]
    except (ValueError, KeyError, TypeError):        # eski biçim: "numara|kod" satırları
        pairs = []
        for answer in raw.splitlines():
            m = re.match(r"\s*(\d+)\s*\|\s*([\d-]+)", answer)
            if m:
                pairs.append((int(m.group(1)), m.group(2)))
    rows, failed, score = {}, [], {}
    for idx, loinc in pairs:
        if not 1 <= idx <= len(lines):
            continue
        line = lines[idx - 1]
        parsed = parse_line(line, units[loinc]) if loinc in units else None
        if parsed is None:
            failed.append(idx)
            continue
        fixed = False
        if repair:                                    # ad tutarlılığı kontrolü
            new = name_check(line, loinc, units)
            if new != loinc and parse_line(line, units[new]):
                loinc, parsed, fixed = new, parse_line(line, units[new]), True
        sim = name_similarity(line_label(line), loinc) if repair else 0.0
        if repair and loinc in rows:                  # aynı tahlile iki satır: adı daha iyi uyan kalır
            if sim <= score[loinc]:
                failed.append(idx)
                continue
            failed.append(rows[loinc]["line"])
        value, unit, low, high = parsed
        rows[loinc] = {"loinc": loinc, "value": value, "unit": unit, "low": low, "high": high,
                       "flag": flag(value, low, high), "line": idx}
        if fixed:
            rows[loinc]["repaired"] = True
        score[loinc] = sim
    if repair:                                        # ikinci tur: birim onarımı
        for idx in failed:
            code = repair_code(lines[idx - 1], units)
            if code is None or code in rows:
                continue
            parsed = parse_line(lines[idx - 1], units[code])
            if parsed:
                value, unit, low, high = parsed
                rows[code] = {"loinc": code, "value": value, "unit": unit, "low": low, "high": high,
                              "flag": flag(value, low, high), "repaired": True, "line": idx}
    return list(rows.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--n", type=int, default=5, help="dil başına rapor sayısı")
    ap.add_argument("--folder", default="data/reports_messy")
    args = ap.parse_args()

    tests = pd.read_csv("data/tests.csv")
    units = canonical_units()
    instructions = build_instructions(tests)
    schema = answer_schema(units.keys())
    out = Path("results") / (args.model.replace(":", "_").replace("/", "_") + "_hybrid_json")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.model}, biçim: hybrid (JSON şemalı)  →  {out}\n")

    for lang in LANGS:
        for i in range(1, args.n + 1):
            stem = f"{lang}_{i:03d}"
            target = out / f"{stem}.json"
            if target.exists():
                print(f"{stem}: zaten var, atlandı")
                continue
            report = (Path(args.folder) / f"{stem}.txt").read_text(encoding="utf-8")
            start = time.time()
            try:
                raw = ask_model(args.model, instructions, numbered(candidate_lines(report)), schema)
            except urllib.error.URLError:
                print("\nOllama'ya bağlanılamadı. Ollama açık mı? Görev çubuğunda lama simgesi olmalı.")
                return
            seconds = time.time() - start
            rows = rows_from_answer(raw, report, units)
            target.write_text(json.dumps(
                {"model": args.model, "mode": "hybrid", "seconds": round(seconds, 1),
                 "raw": raw, "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{stem}: {len(rows):>2}/30 satır okundu, {seconds:.0f} sn")


if __name__ == "__main__":
    main()
