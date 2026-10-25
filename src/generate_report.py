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


def has(x):
    """Sınır var mı? CSV'de boş hücreler NaN gelir."""
    return not pd.isna(x)


def pick_value(low, high):
    """Çoğunlukla normal, bazen düşük ya da yüksek bir değer seçer."""
    lo = low if has(low) else high * 0.5
    hi = high if has(high) else low * 2
    r = random.random()
    if r < 0.6:
        return random.uniform(lo, hi)
    elif r < 0.8 and has(low):
        return random.uniform(low * 0.6, low)
    elif has(high):
        return random.uniform(high, high * 1.5)
    else:
        return random.uniform(lo, hi)


def flag(value, low, high):
    """L düşük, H yüksek, N normal. Sadece var olan sınır kontrol edilir."""
    if has(low) and value < low:
        return "L"
    elif has(high) and value > high:
        return "H"
    else:
        return "N"


def format_num(x, lang):
    """Sayıyı dile göre yazar: İngilizcede nokta, diğerlerinde virgül."""
    s = f"{x:.1f}"
    if lang != "en":
        s = s.replace(".", ",")
    return s


def format_range(low, high, lang):
    """Referans aralığı: (a - b), (< b) ya da (> a)."""
    if has(low) and has(high):
        return f"({format_num(low, lang)} - {format_num(high, lang)})"
    elif has(high):
        return f"(< {format_num(high, lang)})"
    else:
        return f"(> {format_num(low, lang)})"


def to_json(x):
    """NaN'ı None'a (JSON'da null) çevirir; geçerli JSON için gerekli."""
    return float(x) if has(x) else None


def make_report(tests, lang):
    """Tek bir dilde bir rapor metni ve doğru cevaplarını üretir."""
    lines = [TITLES[lang], ""]
    truth = []
    for _, t in tests.iterrows():
        value = round(pick_value(t.low, t.high), 1)
        name = t[f"name_{lang}"]                 # yeni: dile göre tahlil adı
        lines.append(f"{name:<20}{format_num(value, lang):>8} {t.unit:<9}"
                     f"{format_range(t.low, t.high, lang)}")
        truth.append({"loinc": t.loinc, "value": value, "unit": t.unit,
                      "low": to_json(t.low), "high": to_json(t.high),
                      "flag": flag(value, t.low, t.high)})
    return "\n".join(lines), truth


def main(n_per_lang=25):
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