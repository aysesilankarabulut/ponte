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
        "stream": False,
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


def parse_line(line, unit):
    """Bir satırdan değeri ve aralığı çıkarır. Bulamazsa None döndürür.
    Yöntem: satırda birimi bul → önceki son sayı değer, sonrası aralık."""
    pos = _key(line).rfind(_key(unit))
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


def rows_from_answer(raw, report, units):
    """Modelin 'numara|LOINC' cevabını ve rapor metnini birleştirip tabloyu kurar."""
    lines = candidate_lines(report)
    try:                                              # yeni biçim: JSON
        pairs = [(int(x["n"]), str(x["code"])) for x in json.loads(raw)["lines"]]
    except (ValueError, KeyError, TypeError):        # eski biçim: "numara|kod" satırları
        pairs = []
        for answer in raw.splitlines():
            m = re.match(r"\s*(\d+)\s*\|\s*([\d-]+)", answer)
            if m:
                pairs.append((int(m.group(1)), m.group(2)))
    rows = {}
    for idx, loinc in pairs:
        if loinc not in units or not 1 <= idx <= len(lines):
            continue
        parsed = parse_line(lines[idx - 1], units[loinc])
        if parsed is None:
            continue
        value, unit, low, high = parsed
        rows[loinc] = {"loinc": loinc, "value": value, "unit": unit,
                       "low": low, "high": high, "flag": flag(value, low, high)}
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
