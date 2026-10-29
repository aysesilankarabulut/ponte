"""Karşılaştırma: kural tabanlı okuyucu ile dil modelini AYNI raporlarda ölçer.

Kullanım:
  python src/compare.py results/llama3.2_3b
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from evaluate import score_report
from parse_rules import build_name_map, canonical_units, parse_report
from read_hybrid import rows_from_answer
from read_llm import parse_output


def missed_abnormal(rows, truth):
    """En tehlikeli hata: gerçekte yüksek/düşük olan değere 'normal' denmesi (ya da hiç okunmaması)."""
    pred = {r["loinc"]: r["flag"] for r in rows}
    return sum(1 for t in truth if t["flag"] != "N" and pred.get(t["loinc"], "N") == "N")


def main(pred_dir, folder="data/reports_messy"):
    preds = sorted(Path(pred_dir).glob("*.json"))
    if not preds:
        print(f"{pred_dir} içinde hiç tahmin yok. Önce read_llm.py'yi çalıştır.")
        return
    name_map, units = build_name_map(), canonical_units()
    stats = defaultdict(lambda: {"rules": [0, 0], "llm": [0, 0]})   # dil → [doğru, toplam]
    seconds, danger = [], {"rules": 0, "llm": 0}

    for pf in preds:
        llm = json.loads(pf.read_text(encoding="utf-8"))
        gold = json.loads((Path(folder) / pf.name).read_text(encoding="utf-8"))
        text = (Path(folder) / pf.with_suffix(".txt").name).read_text(encoding="utf-8")
        rules, _ = parse_report(text, name_map, units)
        # ham cevabı güncel ayrıştırıcıyla yeniden oku
        if llm.get("mode") == "hybrid":
            llm_rows = rows_from_answer(llm["raw"], text, units)
        else:
            llm_rows = parse_output(llm["raw"], units)
        for reader, rows in (("rules", rules), ("llm", llm_rows)):
            correct, total, _, _ = score_report(rows, gold["results"])
            stats[gold["lang"]][reader][0] += correct
            stats[gold["lang"]][reader][1] += total
            danger[reader] += missed_abnormal(rows, gold["results"])
        seconds.append(llm["seconds"])

    first = json.loads(preds[0].read_text(encoding="utf-8"))
    print(f"{len(preds)} dağınık rapor, model: {first['model']}, biçim: {first.get('mode', 'report')}\n")
    print(f"{'Dil':<6}{'Kurallar':>12}{'Dil modeli':>14}")
    total = {"rules": [0, 0], "llm": [0, 0]}
    for lang, s in sorted(stats.items()):
        print(f"{lang:<6}{s['rules'][0] / s['rules'][1]:>11.1%}{s['llm'][0] / s['llm'][1]:>14.1%}")
        for reader in total:
            total[reader][0] += s[reader][0]
            total[reader][1] += s[reader][1]
    print(f"{'Genel':<6}{total['rules'][0] / total['rules'][1]:>11.1%}"
          f"{total['llm'][0] / total['llm'][1]:>14.1%}")
    abnormal = sum(1 for pf in preds for t in json.loads(
        (Path(folder) / pf.name).read_text(encoding="utf-8"))["results"] if t["flag"] != "N")
    print(f"{'Kaçırılan anormal':<18}{danger['rules']:>5}{danger['llm']:>14}   (toplam {abnormal} anormal değerden)")
    print(f"\nDil modeli: rapor başına ortalama {sum(seconds) / len(seconds):.0f} sn")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/llama3.2_3b")
