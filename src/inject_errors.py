"""Hata ekleme deneyi: doğrulama katmanı bilerek bozulmuş cümlelerin kaçını yakalıyor?

Her normal dışı tahlil için doğru bir cümle alınır, sonra dört şekilde bozulur:
  - sayı:    değer %10–40 değiştirilir
  - yön:     "düşük" ile "yüksek" yer değiştirir
  - normal:  cümleye "Değeri normal aralığındadır." eklenir (gerçek bir model hatası)
  - teşhis:  cümleye uydurma bir teşhis eklenir
  - küçümseme: cümleye "endişelenmeyin" türü bir ifade eklenir
Bozulmamış cümleler de denenir: haksız yere reddedilenler "yanlış alarm" sayılır.

Kaynak cümleler:
  --source code   → kodun yazdığı şablon cümleler (her bilgisayarda hemen çalışır)
  --source model  → dil modelinin yazıp doğrulamadan geçen gerçek cümleleri
                    (önce explain.py çalıştırılmış olmalı)
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

import pandas as pd

from explain import build_facts
from verify import check_sentence, fallback_sentence, fmt

DIAGNOSES = ["Bu sonuç anemi olduğunuzu gösteriyor.", "Bu, diyabet belirtisidir.",
             "Bu değer kanser riskine işaret eder."]
REASSURE = ["Ama endişelenmeyin, önemli değil.", "Merak etmeyin, tehlikeli değil."]


def corrupt(sentence, fact, kind, rng):
    text = sentence["text"]
    if kind == "sayı":
        wrong = fact["value"] * rng.choice([0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4])
        for written in (fmt(fact["value"]), f"{fact['value']:.1f}"):   # virgüllü ya da noktalı
            if written in text:
                return text.replace(written, fmt(wrong) if "," in written else f"{wrong:.1f}")
        return None
    if kind == "yön":
        swap = {"altında": "üstünde", "üstünde": "altında", "düşük": "yüksek", "yüksek": "düşük",
                "altındadır": "üstündedir", "üstündedir": "altındadır"}
        for a, b in swap.items():
            if a in text:
                return text.replace(a, b)
        return None
    if kind == "normal":           # normal dışı değere "normal" demek
        return f"{text} Değeri normal aralığındadır."
    if kind == "teşhis":
        return f"{text} {rng.choice(DIAGNOSES)}"
    return f"{text} {rng.choice(REASSURE)}"


def source_sentences(args, names):
    """(cümle, gerçekler) çiftlerini üretir."""
    if args.source == "code":
        for jf in sorted(Path("data/reports_messy").glob("*.json")):
            facts = build_facts(json.loads(jf.read_text(encoding="utf-8"))["results"], names)
            for code, f in facts.items():
                if f["flag"] != "N":
                    yield {"fact": code, "text": fallback_sentence(f)}, facts
    else:
        rejected = 0
        for jf in sorted(Path(args.folder).glob("*.json")):
            d = json.loads(jf.read_text(encoding="utf-8"))
            for s in json.loads(d["raw"])["sentences"]:     # modelin ham cümleleri
                if s["fact"] not in d["facts"]:
                    continue
                if check_sentence(s, d["facts"]):           # zaten hatalı: modelin kendi hatası
                    rejected += 1
                    continue
                yield s, d["facts"]
        print(f"Modelin kendi hatalı cümleleri (deneye alınmadı): {rejected}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["code", "model"], default="code")
    ap.add_argument("--folder", default="results/explanations/llama3.1_8b")
    args = ap.parse_args()
    names = pd.read_csv("data/names_tr.csv").set_index("loinc").to_dict("index")
    rng = random.Random(1)
    caught, tried = Counter(), Counter()
    for sentence, facts in source_sentences(args, names):
        fact = facts[sentence["fact"]]
        tried["temiz"] += 1
        caught["temiz"] += check_sentence(sentence, facts) is not None   # yanlış alarm
        for kind in ["sayı", "yön", "normal", "teşhis", "küçümseme"]:
            bad = corrupt(sentence, fact, kind, rng)
            if bad is None or bad == sentence["text"]:
                continue
            tried[kind] += 1
            hit = check_sentence({**sentence, "text": bad}, facts) is not None
            caught[kind] += hit
            if not hit:
                print(f"  KAÇTI ({kind}): {bad}")

    print(f"Kaynak: {args.source}\n")
    print(f"{'Hata türü':<12}{'Denenen':>9}{'Yakalanan':>11}{'Oran':>8}")
    for kind in ["sayı", "yön", "normal", "teşhis", "küçümseme"]:
        if tried[kind]:
            print(f"{kind:<12}{tried[kind]:>9}{caught[kind]:>11}{caught[kind] / tried[kind]:>8.0%}")
    print(f"\nYanlış alarm (temiz cümle reddedildi): {caught['temiz']}/{tried['temiz']}")


if __name__ == "__main__":
    main()
