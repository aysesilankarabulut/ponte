"""Kural tabanlı okuyucu: rapor metnini satır satır tabloya döker.

Yapay zeka kullanmaz; düzenli ifadeler (regex) ve bir test adı sözlüğüyle çalışır.
İleride dil modeliyle yapılan okumayı bununla karşılaştıracağız.
"""
import re
import pandas as pd

LANGS = ["it", "de", "en", "es"]

# Bir rapor satırının kalıbı:  <ad>  <değer> <birim> (<aralık>)
LINE_RE = re.compile(
    r"^(?P<name>.+?)\s{2,}"          # test adı, ardından en az 2 boşluk
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s+"  # değer: 12,8 ya da 12.8
    r"(?P<unit>\S+)\s+"              # birim: boşluk içermez
    r"\((?P<range>[^()]*)\)\s*$"     # parantez içindeki referans aralığı
)


def to_float(s):
    """'12,8' ya da '12.8' yazısını 12.8 sayısına çevirir."""
    return float(s.replace(",", "."))


def parse_range(text):
    """'12,0 - 16,0' → (12.0, 16.0);  '< 200,0' → (None, 200.0);  '> 40,0' → (40.0, None)"""
    text = text.strip()
    if text.startswith("<"):
        return None, to_float(text[1:].strip())
    if text.startswith(">"):
        return to_float(text[1:].strip()), None
    low, high = text.split(" - ")
    return to_float(low), to_float(high)


def build_name_map(tests_csv="data/tests.csv"):
    """Dört dildeki her test adını LOINC koduna eşleyen sözlük kurar."""
    tests = pd.read_csv(tests_csv)
    name_map = {}
    for _, t in tests.iterrows():
        for lang in LANGS:
            name_map[t[f"name_{lang}"].strip().lower()] = t.loinc
    return name_map


def canonical_units(tests_csv="data/tests.csv"):
    """Her LOINC kodu için standart birimi döndürür (ör. 718-7 → g/dL)."""
    tests = pd.read_csv(tests_csv)
    return dict(zip(tests.loinc, tests.unit))


def normalize_unit(raw, canonical):
    """Yazım farkı olan birimi standart hale getirir: 'mg/dl' → 'mg/dL', '10^3/uL' → '10^3/µL'.
    Gerçekten farklı bir birimse (ör. mmol/L yerine mg/dL) olduğu gibi bırakır."""
    def key(u):
        return u.lower().replace("µ", "u").replace("μ", "u")
    return canonical if key(raw) == key(canonical) else raw


def flag(value, low, high):
    """L düşük, H yüksek, N normal. Olmayan sınır kontrol edilmez."""
    if low is not None and value < low:
        return "L"
    if high is not None and value > high:
        return "H"
    return "N"


def parse_report(text, name_map, units=None):
    """Bir rapor metnini satır listesine çevirir; tanınmayan satırları ayrıca döndürür."""
    units = units or canonical_units()
    rows, unknown = [], []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue                      # başlık ya da boş satır
        name = m["name"].strip()
        loinc = name_map.get(name.lower())
        if loinc is None:
            unknown.append(name)          # sözlükte olmayan test adı
            continue
        try:
            value = to_float(m["value"])
            low, high = parse_range(m["range"])
        except ValueError:
            unknown.append(name)          # aralık ya da değer beklenen biçimde değil
            continue
        unit = normalize_unit(m["unit"], units[loinc])
        rows.append({"loinc": loinc, "value": value, "unit": unit,
                     "low": low, "high": high, "flag": flag(value, low, high)})
    return rows, unknown


if __name__ == "__main__":
    # Hızlı deneme: bir raporu okuyup ilk 5 satırı göster
    from pathlib import Path
    text = Path("data/reports/de_001.txt").read_text(encoding="utf-8")
    rows, unknown = parse_report(text, build_name_map())
    print(pd.DataFrame(rows).head())
    print(f"\n{len(rows)} satır okundu, tanınmayan: {unknown}")
