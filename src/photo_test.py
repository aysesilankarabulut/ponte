"""Fotoğraftan okuma deneyi: 60 yeni raporun 'telefon fotoğrafı' halini baştan sona okur.

Akış (web arayüzüyle aynı): fotoğraf → Tesseract OCR → OCR temizliği → 8B karma okuyucu
(tek birimli satırlar kodla + ad/birim onarımı) → doğru cevaplarla karşılaştırma.
Fotoğraflar:  python src/make_photos.py   (data/photos_final, bir kez)

Kullanım:
  python src/photo_test.py                (~2 saat, kaldığı yerden devam eder)
  python src/photo_test.py --report-only  (sadece sonuç tablosu)
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import ocr
import pipeline as p
from compare import missed_abnormal
from evaluate import score_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--photos", default="data/photos_final")
    ap.add_argument("--gold", default="data/reports_final")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    out = Path("results/final_photo") / args.model.replace(":", "_")
    out.mkdir(parents=True, exist_ok=True)
    photos = sorted(Path(args.photos).glob("*.jpg"))
    if not args.report_only:
        ok, msg = ocr.status()
        if not ok:
            print(msg)
            return
        p.warm_up(args.model)
        for i, ph in enumerate(photos, 1):
            target = out / f"{ph.stem}.json"
            if target.exists():
                continue
            t0 = time.time()
            text, _ = ocr.file_to_text(ph.name, ph.read_bytes())
            t1 = time.time()
            r = p.read_report(text, args.model, direct=True)
            target.write_text(json.dumps({"ocr_seconds": round(t1 - t0, 1), "read_seconds": round(time.time() - t1, 1),
                                          "ocr_text": text, "rows": r["rows"], "unread": r["unread"]},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{i}/{len(photos)}] {ph.stem}: {len(r['rows'])} tahlil, {len(r['unread'])} okunamadı uyarısı, "
                  f"OCR {t1 - t0:.0f} sn + okuma {time.time() - t1:.0f} sn", flush=True)

    by = defaultdict(lambda: [0, 0])
    miss = ab = unread = wrong = n = 0
    ocr_s, read_s = [], []
    for ph in photos:
        target = out / f"{ph.stem}.json"
        if not target.exists():
            continue
        pred = json.loads(target.read_text(encoding="utf-8"))
        gold = json.loads((Path(args.gold) / f"{ph.stem}.json").read_text(encoding="utf-8"))
        c, t, _, _ = score_report(pred["rows"], gold["results"])
        for key in ("Genel", f"dil: {gold['lang']}", f"biçim: {gold['style']}"):
            by[key][0] += c
            by[key][1] += t
        miss += missed_abnormal(pred["rows"], gold["results"])
        ab += sum(g["flag"] != "N" for g in gold["results"])
        unread += len(pred["unread"])
        g = {x["loinc"]: x for x in gold["results"]}
        wrong += sum(1 for r in pred["rows"] if r["loinc"] in g and abs(r["value"] - g[r["loinc"]]["value"]) > 1e-6)
        n += 1
        ocr_s.append(pred["ocr_seconds"])
        read_s.append(pred["read_seconds"])
    if not n:
        print("Henüz sonuç yok.")
        return
    print(f"\n========== FOTOĞRAF TESTİ: {n} fotoğraf, {args.model} ==========")
    for key, (c, t) in sorted(by.items(), key=lambda kv: (kv[0] != "Genel", kv[0])):
        print(f"{key:<20}{c / t:>8.1%}")
    print(f"Kaçırılan anormal değer: {miss}/{ab}")
    print(f"Yanlış okunan değer (tahlil doğru, sayı yanlış): {wrong}")
    print(f"Kullanıcıya gösterilen 'okunamadı' uyarısı: {unread}")
    print(f"Ortalama süre: OCR {sum(ocr_s) / n:.0f} sn + okuma {sum(read_s) / n:.0f} sn")


if __name__ == "__main__":
    main()
