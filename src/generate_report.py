import json
import random
import pandas as pd


def pick_value(low, high):
    """Çoğunlukla normal, bazen düşük ya da yüksek bir değer seçer."""
    r = random.random()                          # 0 ile 1 arasında rastgele sayı
    if r < 0.6:                                  # %60 ihtimalle: normal değer
        return random.uniform(low, high)
    elif r < 0.8:                                # %20 ihtimalle: düşük değer
        return random.uniform(low * 0.6, low)
    else:                                        # %20 ihtimalle: yüksek değer
        return random.uniform(high, high * 1.5)


def flag(value, low, high):
    """Değerin normal aralığa göre durumunu verir: L düşük, H yüksek, N normal."""
    if value < low:
        return "L"
    elif value > high:
        return "H"
    else:
        return "N"


def format_it(x):
    """İtalyan biçimi: ondalık virgül, bir basamak."""
    return f"{x:.1f}".replace(".", ",")


def main():
    tests = pd.read_csv("data/tests.csv")       # test listesini tablo olarak oku
    lines, truth = [], []
    for _, t in tests.iterrows():                # her tahlil için bir satır
        value = round(pick_value(t.low, t.high), 1)
        lines.append(f"{t.name_it:<14}{format_it(value):>8} {t.unit:<9}({format_it(t.low)} - {format_it(t.high)})")
        truth.append({"loinc": t.loinc, "value": value, "unit": t.unit,
                      "low": t.low, "high": t.high, "flag": flag(value, t.low, t.high)})
    print("\n".join(lines))                      # raporu ekrana yaz
    with open("data/report_001.json", "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)   # doğru cevabı dosyaya kaydet


if __name__ == "__main__":
    main()