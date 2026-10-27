"""Dil modeli okuyucusu: rapor metnini bilgisayarda çalışan bir modele (Ollama) okutur.

İş bölümü:
  - Dil modeli: test adını tanır (her dilde, kısaltma ve OCR hatasıyla bile) ve
    değer / birim / aralığı satırdan çeker.
  - Kod: sayıları çevirir, birimi standartlaştırır ve normal dışı bayrağını hesaplar.
Model yavaş olduğu için her cevap results/<model>/ klasörüne kaydedilir;
yarıda kesilirse tekrar çalıştırınca kaldığı yerden devam eder.

Kullanım:
  python src/read_llm.py                      → llama3.2:3b, dil başına 5 rapor
  python src/read_llm.py --model gemma3:4b --n 10
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from generate_report import LANGS
from parse_rules import canonical_units, flag, normalize_unit, to_float

OLLAMA_URL = "http://localhost:11434/api/chat"


def build_instructions(tests):
    """Modele verilecek talimat: görev, bilinen test listesi ve bir örnek."""
    known = "\n".join(f"{t.loinc} = {t.name_en}" for _, t in tests.iterrows())
    return f"""You extract laboratory results from a lab report.
The report may be in Italian, German, English or Spanish. It may use abbreviations
(e.g. Hb, GPT), upper case, OCR typos (0 instead of o, 1 instead of l) and different layouts.

Known tests (LOINC code = English name):
{known}

For every test result in the report, output exactly one line:
LOINC|value|unit|low|high
- LOINC: the code from the list above
- value: the measured number as written (decimal comma or point)
- unit: the unit as written in the report
- low, high: the reference range limits. Write - for a missing limit:
  "< 200" or "up to 200" means low is - and high is 200; "> 40" means low is 40 and high is -.
Ignore titles, patient data, section headers and page numbers.
Output only these lines, nothing else.

Example report:
HEMOGLOBIN     Result: 10.2   g/dL    Normal: 12.0-16.0
Total chol.    269.8 mg/dL   max 200
Example output:
718-7|10.2|g/dL|12.0|16.0
2093-3|269.8|mg/dL|-|200.0"""


def ask_model(model, instructions, report):
    """Ollama'ya raporu gönderir, modelin ham cevabını döndürür."""
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Report:\n{report}\n\nOutput:"},
        ],
        "options": {"temperature": 0, "num_ctx": 4096},   # sıcaklık 0: her seferinde aynı cevap
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read())["message"]["content"]


NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def read_number(text):
    """'12,8', '<200', '8,1 10^6/µL' gibi yazılardan İLK sayıyı çıkarır; sayı yoksa None."""
    m = NUMBER_RE.search(text)
    return to_float(m.group()) if m else None


def split_value_unit(text):
    """Model bazen değer alanına birimi de yazıyor: '8,1 10^6/µL' → ('8,1', '10^6/µL')."""
    m = NUMBER_RE.search(text)
    if not m:
        return text, ""
    return m.group(), text[m.end():].strip(" *")


def parse_output(raw, units):
    """Modelin satırlarını tabloya çevirir. Bozuk ya da bilinmeyen satırları atlar."""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)   # "düşünen" modellerin notlarını at
    rows = {}
    for line in raw.splitlines():
        parts = [p.strip() for p in line.strip().strip("`").split("|")]
        if len(parts) != 5 or parts[0] not in units:
            continue
        number, unit_in_value = split_value_unit(parts[1])
        value = read_number(number)
        if value is None:
            continue
        low, high = read_number(parts[3]), read_number(parts[4])
        unit = unit_in_value or parts[2]          # değer alanındaki birim daha eksiksiz
        rows[parts[0]] = {"loinc": parts[0], "value": value,
                          "unit": normalize_unit(unit, units[parts[0]]),
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
    out = Path("results") / args.model.replace(":", "_").replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.model}  →  {out}\n")

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
                raw = ask_model(args.model, instructions, report)
            except urllib.error.URLError:
                print("\nOllama'ya bağlanılamadı. Ollama açık mı? Görev çubuğunda lama simgesi olmalı.")
                return
            seconds = time.time() - start
            rows = parse_output(raw, units)
            target.write_text(json.dumps(
                {"model": args.model, "seconds": round(seconds, 1), "raw": raw, "results": rows},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{stem}: {len(rows):>2}/30 satır okundu, {seconds:.0f} sn")


if __name__ == "__main__":
    main()
