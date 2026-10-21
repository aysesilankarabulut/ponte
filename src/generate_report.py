import json
import random
from pathlib import Path
import pandas as pd

LANGS = ["it", "de", "en", "es"]                 # yeni: 4 belge dili
TITLES = {                                       # yeni: her dilde rapor başlığı
    "it": "Esami di laboratorio",
    "de": "Laborbefund",
    "en": "Laboratory results",
    "es": "Resultados de laboratorio",
}


def pick_value(low, high):
    """Çoğunlukla normal, bazen düşük ya da yüksek bir değer seçer."""
    r = random.random()
    if r < 0.6:
        return random.uniform(low, high)
    elif r < 0.8:
        return random.uniform(low * 0.6, low)
    else:
        return random.uniform(high, high * 1.5)


def flag(value, low, high):
    """L düşük, H yüksek, N normal."""
    if value < low:
        return "L"
    elif value > high:
        return "H"
    else:
        return "N"


def format_num(x, lang):
    """Sayıyı dile göre yazar: İngilizcede nokta, diğerlerinde virgül."""
    s = f"{x:.1f}"
    if lang != "en":
        s = s.replace(".", ",")
    return s


def make_report(tests, lang):
    """Tek bir dilde bir rapor metni ve doğru cevaplarını üretir."""
    lines = [TITLES[lang], ""]
    truth = []
    for _, t in tests.iterrows():
        value = round(pick_value(t.low, t.high), 1)
        name = t[f"name_{lang}"]                 # yeni: dile göre tahlil adı
        lines.append(f"{name:<20}{format_num(value, lang):>8} {t.unit:<9}"
                     f"({format_num(t.low, lang)} - {format_num(t.high, lang)})")
        truth.append({"loinc": t.loinc, "value": value, "unit": t.unit,
                      "low": t.low, "high": t.high, "flag": flag(value, t.low, t.high)})
    return "\n".join(lines), truth


def main(n_per_lang=5):
    random.seed(42)                              # yeni: her çalıştırmada aynı veri çıksın
    tests = pd.read_csv("data/tests.csv")
    out = Path("data/reports")
    out.mkdir(parents=True, exist_ok=True)       # yeni: raporlar için klasör
    for lang in LANGS:
        for i in range(1, n_per_lang + 1):
            text, truth = make_report(tests, lang)
            stem = f"{lang}_{i:03d}"             # ör. it_001, de_003
            (out / f"{stem}.txt").write_text(text, encoding="utf-8")
            (out / f"{stem}.json").write_text(
                json.dumps({"lang": lang, "results": truth}, ensure_ascii=False, indent=2),
                encoding="utf-8")
    print(f"{len(LANGS) * n_per_lang} rapor üretildi: {out}\n")
    print((out / "de_001.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()