"""Hız testi: arayüzdeki adımları farklı ayarlarla aynı raporda ölçer.

Kullanım:  python src/speed_test.py            (it_010 raporu, llama3.1:8b; ~20-25 dakika)
           python src/speed_test.py --report de_011
"""
import argparse
import json
import time
from pathlib import Path

import pipeline as p
from evaluate import score_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--report", default="it_010")
    args = ap.parse_args()
    text = Path(f"data/reports_messy/{args.report}.txt").read_text(encoding="utf-8")
    gold = json.loads(Path(f"data/reports_messy/{args.report}.json").read_text(encoding="utf-8"))
    lang = p.detect_lang(text)
    out = {}

    def step(name, fn):
        print(f"... {name}", flush=True)
        t = time.time(); r = fn(); out[name] = time.time() - t
        print(f"    {out[name]:.0f} sn", flush=True)
        return r

    step("model yükleme", lambda: p.warm_up(args.model))
    a = step("okuma (hepsi modele)", lambda: p.read_report(text, args.model))
    b = step("okuma (tek birimliler kodla)", lambda: p.read_report(text, args.model, direct=True))
    e1 = step("açıklama (tek istek)", lambda: p.explain_rows(b["rows"], args.model, chunks=1))
    e3 = step("açıklama (3 paralel istek)", lambda: p.explain_rows(b["rows"], args.model, chunks=3))
    step("doktor soruları", lambda: p.doctor_questions(e1["facts"], lang, args.model))

    acc = lambda rows: "%d/%d alan doğru" % score_report(rows, gold["results"])[:2]
    print("\n================ SONUÇ ================")
    for k, v in out.items():
        print(f"{k:<32}{v:>6.0f} sn")
    print(f"\nokuma doğruluğu: hepsi modele {acc(a['rows'])} | kodla {acc(b['rows'])} "
          f"(modele sorulan satır {a['asked']} → {b['asked']})")
    print(f"açıklama reddedilen: tek istek {len(e1['rejected'])} | 3 paralel {len(e3['rejected'])}")


if __name__ == "__main__":
    main()
