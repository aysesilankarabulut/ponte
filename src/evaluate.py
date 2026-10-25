"""Değerlendirici: bir okuyucunun çıktısını doğru cevaplarla (JSON) karşılaştırır.

Her alan ayrı ayrı puanlanır: değer, birim, alt sınır, üst sınır, bayrak.
Aynı değerlendiriciyi ileride yapay zekalı okuyucu için de kullanacağız.
"""
import json
from collections import defaultdict
from pathlib import Path

from parse_rules import build_name_map, parse_report

FIELDS = ["value", "unit", "low", "high", "flag"]


def same(a, b):
    """İki alan aynı mı? Sayılarda küçük yuvarlama farklarını yok sayar."""
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) < 1e-6
    return a == b


def score_report(predicted, truth):
    """Bir raporun puanını sayar: doğru alan sayısı, toplam alan, eksik ve fazla satır."""
    pred_by_code = {r["loinc"]: r for r in predicted}
    correct = total = missing = 0
    for t in truth:
        total += len(FIELDS)
        p = pred_by_code.get(t["loinc"])
        if p is None:
            missing += 1                  # bu tahlil hiç okunamamış
            continue
        correct += sum(same(p[f], t[f]) for f in FIELDS)
    extra = len(set(pred_by_code) - {t["loinc"] for t in truth})
    return correct, total, missing, extra


def main(folder="data/reports"):
    print(f"Klasör: {folder}\n")
    name_map = build_name_map()
    stats = defaultdict(lambda: [0, 0, 0, 0])   # dil → [doğru, toplam, eksik, fazla]
    for jf in sorted(Path(folder).glob("*.json")):
        gold = json.loads(jf.read_text(encoding="utf-8"))
        text = jf.with_suffix(".txt").read_text(encoding="utf-8")
        predicted, _ = parse_report(text, name_map)
        for i, n in enumerate(score_report(predicted, gold["results"])):
            stats[gold["lang"]][i] += n

    print(f"{'Dil':<6}{'Alan doğruluğu':>16}{'Eksik satır':>13}{'Fazla satır':>13}")
    all_c = all_t = 0
    for lang, (c, t, miss, extra) in stats.items():
        print(f"{lang:<6}{c / t:>15.1%}{miss:>13}{extra:>13}")
        all_c, all_t = all_c + c, all_t + t
    print(f"\nGenel alan doğruluğu: {all_c / all_t:.1%}")


if __name__ == "__main__":
    import sys
    # Kullanım: python src/evaluate.py                     → temiz raporlar
    #           python src/evaluate.py data/reports_messy  → dağınık raporlar
    main(sys.argv[1] if len(sys.argv) > 1 else "data/reports")
