"""Daraltmalı karma okuyucu: KOD seçenekleri daraltır, MODEL aralarından seçer.

Fikir: Her satırda önce kod, hangi birimin geçtiğine bakar.
  - Birim tek bir tahlile aitse (ör. pg/mL → sadece B12), model hiç sorulmaz.
  - Birim birkaç tahlilde ortaksa (ör. 10^3/µL → lökosit ya da trombosit),
    model sadece o birkaç seçenek arasından seçer.
  - Satırda bilinen bir birim yoksa (hasta adı, tarih, sayfa no.) satır atlanır.
Modelin cevabı seçeneklerin dışındaysa kod onu reddeder (doğrulama).

Sonuçlar results/<model>_narrow/ klasörüne gider; compare.py ile ölçülür.

Kullanım:
  python src/read_narrow.py                       → llama3.2:3b, dil başına 5 rapor
  python src/read_narrow.py --model llama3.1:8b
"""
import argparse
import json
import time
import urllib.error
from pathlib import Path

import pandas as pd

from generate_report import LANGS
from parse_rules import canonical_units
from read_hybrid import answer_schema, ask_model, find_unit, rows_from_answer
from read_llm import candidate_lines


def build_instructions():
    return """You classify the lines of a laboratory report.
The report may be in Italian, German, English or Spanish. Test names may be abbreviated
(e.g. Hb, GPT), upper case, or contain OCR typos (0 instead of o, 1 instead of l).

Each input line starts with a number and ends with its options in square brackets.
For EVERY input line choose the LOINC code of the test on that line from ITS options,
or NONE if none of the options fits. Answer in JSON.

Example input:
4: TRANSAMINASI GPT   35 U/L   v.r. < 40   [options: 1742-6 = ALT | 1920-8 = AST | 2324-2 = GGT]
7: Leucociti   5,2 10^3/uL (4,0 - 10,0)   [options: 6690-2 = White blood cells | 777-3 = Platelets]
Example output:
{"lines": [{"n": 4, "code": "1742-6"}, {"n": 7, "code": "6690-2"}]}"""


def options_for(line, units, names):
    """Satırda geçen birimlere göre olası tahlilleri döndürür."""
    return [code for code, unit in units.items() if find_unit(line, unit) >= 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--n", type=int, default=5, help="dil başına rapor sayısı")
    ap.add_argument("--folder", default="data/reports_messy")
    args = ap.parse_args()

    tests = pd.read_csv("data/tests.csv")
    units = canonical_units()
    names = dict(zip(tests.loinc, tests.name_en))
    instructions = build_instructions()
    schema = answer_schema(units.keys())
    out = Path("results") / (args.model.replace(":", "_").replace("/", "_") + "_narrow")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.model}, biçim: daraltmalı karma  →  {out}\n")

    for lang in LANGS:
        for i in range(1, args.n + 1):
            stem = f"{lang}_{i:03d}"
            target = out / f"{stem}.json"
            if target.exists():
                print(f"{stem}: zaten var, atlandı")
                continue
            report = (Path(args.folder) / f"{stem}.txt").read_text(encoding="utf-8")
            direct, ask, options = [], [], {}
            for n, line in enumerate(candidate_lines(report), 1):
                opts = options_for(line, units, names)
                if len(opts) == 1:
                    direct.append({"n": n, "code": opts[0]})           # kod tek başına karar verdi
                elif len(opts) > 1:
                    options[n] = opts
                    listed = " | ".join(f"{c} = {names[c]}" for c in opts)
                    ask.append(f"{n}: {line.strip()}   [options: {listed}]")

            start = time.time()
            model_raw = ""
            if ask:
                try:
                    model_raw = ask_model(args.model, instructions, "\n".join(ask), schema)
                except urllib.error.URLError:
                    print("\nOllama'ya bağlanılamadı. Ollama açık mı? Görev çubuğunda lama simgesi olmalı.")
                    return
            seconds = time.time() - start

            accepted, rejected = [], 0
            try:
                for x in json.loads(model_raw)["lines"] if model_raw else []:
                    n, code = int(x["n"]), str(x["code"])
                    if code in options.get(n, []):
                        accepted.append({"n": n, "code": code})
                    elif code != "NONE":
                        rejected += 1                                    # seçenek dışı cevap
            except (ValueError, KeyError, TypeError):
                pass
            raw = json.dumps({"lines": accepted, "direct": direct})
            rows = rows_from_answer(raw, report, units)
            target.write_text(json.dumps(
                {"model": args.model, "mode": "hybrid", "variant": "narrow",
                 "seconds": round(seconds, 1), "asked_lines": len(ask), "direct_lines": len(direct),
                 "rejected": rejected, "model_raw": model_raw, "raw": raw, "results": rows},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{stem}: {len(rows):>2}/30 satır okundu ({len(direct)} satırı kod, "
                  f"{len(ask)} satırı model), {seconds:.0f} sn")


if __name__ == "__main__":
    main()
