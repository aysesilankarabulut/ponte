"""Son test: bitmiş okuma sistemini (arayüzdeki ayarlarla) HİÇ görülmemiş yeni raporlarda ölçer.

Raporlar yeni bir tohumla (seed 44) üretilir; geliştirme sırasında hiçbirine bakılmadı.
Okuma, web arayüzüyle aynı yoldan yapılır: pipeline.read_report(direct=True) + ad/birim onarımı.

Kullanım:
  python src/generate_messy.py --seed 44 --n 15 --out data/reports_final     (bir kez)
  python src/final_test.py                                                    (~2 saat, kaldığı yerden devam eder)
  python src/final_test.py --report-only                                      (sadece sonuç tablosu)
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import pipeline as p
from compare import missed_abnormal
from evaluate import score_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--folder", default="data/reports_final")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    out = Path("results/final") / args.model.replace(":", "_")
    out.mkdir(parents=True, exist_ok=True)
    reports = sorted(Path(args.folder).glob("*.txt"))
    if not reports:
        print(f"{args.folder} içinde rapor yok. Önce generate_messy.py ile üretin.")
        return
    if not args.report_only:
        p.warm_up(args.model)
        for i, rp in enumerate(reports, 1):
            target = out / f"{rp.stem}.json"
            if target.exists():
                continue
            t = time.time()
            r = p.read_report(rp.read_text(encoding="utf-8"), args.model, direct=True)
            target.write_text(json.dumps({"seconds": round(time.time() - t, 1), "raw": r["raw"],
                                          "rows": r["rows"], "unread": r["unread"]},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{i}/{len(reports)}] {rp.stem}: {len(r['rows'])} tahlil, "
                  f"{len(r['unread'])} okunamayan satır, {time.time() - t:.0f} sn", flush=True)

    by = defaultdict(lambda: [0, 0])
    miss = ab = unread = 0
    secs = []
    for rp in reports:
        target = out / f"{rp.stem}.json"
        if not target.exists():
            continue
        pred = json.loads(target.read_text(encoding="utf-8"))
        gold = json.loads(rp.with_suffix(".json").read_text(encoding="utf-8"))
        c, t, _, _ = score_report(pred["rows"], gold["results"])
        for key in ("Genel", f"dil: {gold['lang']}", f"biçim: {gold['style']}"):
            by[key][0] += c
            by[key][1] += t
        miss += missed_abnormal(pred["rows"], gold["results"])
        ab += sum(g["flag"] != "N" for g in gold["results"])
        unread += len(pred["unread"])
        secs.append(pred["seconds"])
    print(f"\n========== SON TEST: {len(secs)} yeni rapor, {args.model} ==========")
    for key, (c, t) in sorted(by.items(), key=lambda kv: (kv[0] != "Genel", kv[0])):
        print(f"{key:<20}{c / t:>8.1%}")
    print(f"Kaçırılan anormal değer: {miss}/{ab}")
    print(f"Okunamayan satır uyarısı: {unread}")
    print(f"Ortalama okuma süresi: {sum(secs) / len(secs):.0f} sn/rapor")


if __name__ == "__main__":
    main()
