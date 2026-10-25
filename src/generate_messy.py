"""Dağınık rapor üretici: gerçek laboratuvar raporlarına benzeyen, düzensiz raporlar üretir.

Temiz üreticiyle aynı tahlil listesini ve aynı doğru cevap biçimini kullanır;
sadece metnin görünüşü bozulur. Her rapor dört "laboratuvar stilinden" birini alır,
ayrıca satır satır rastgele bozulmalar eklenir:
  - kısaltmalar (Hb, GPT), kırpılmış adlar (Colest. totale), BÜYÜK HARF
  - OCR'ın sık yaptığı harf hataları (Creatin1na)
  - değerin yanında anormallik işareti (*, H, L)
  - küçük harfli ya da µ yerine u ile yazılmış birimler (mg/dl, ug/dL)
  - farklı aralık yazımları (v.r. 12 - 16, fino a 200, [3,5-5,1])
  - başlık, hasta bilgisi, bölüm adları gibi tahlil olmayan satırlar
Hasta adları tamamen uydurmadır; ileride kişisel veri gizleme adımını test etmek için var.
"""
import json
import random
from pathlib import Path
import pandas as pd

from generate_report import LANGS, TITLES, pick_value, flag, to_json, has

STYLES = ["classic", "dots", "colon", "columns"]

# Laboratuvarların sık kullandığı kısaltmalar (LOINC koduna göre)
ABBR = {
    "718-7": "Hb", "789-8": "RBC", "4544-3": "HCT", "787-2": "MCV", "6690-2": "WBC",
    "777-3": "PLT", "2498-4": "Fe", "4548-4": "HbA1c", "2951-2": "Na", "2823-3": "K",
    "17861-6": "Ca", "1742-6": "GPT", "1920-8": "GOT", "2324-2": "GGT", "6768-6": "ALP",
    "1975-2": "BIL-T", "1988-5": "CRP", "3016-3": "TSH", "3024-7": "FT4",
}
OCR_SWAPS = [("l", "1"), ("o", "0"), ("i", "l"), ("e", "c")]

SECTIONS = {"it": ("EMATOLOGIA", "CHIMICA CLINICA"), "de": ("HÄMATOLOGIE", "KLINISCHE CHEMIE"),
            "en": ("HAEMATOLOGY", "CLINICAL CHEMISTRY"), "es": ("HEMATOLOGÍA", "BIOQUÍMICA")}
PATIENT = {"it": ("Paziente", "Data di nascita"), "de": ("Patient", "Geburtsdatum"),
           "en": ("Patient", "Date of birth"), "es": ("Paciente", "Fecha de nacimiento")}
FIRST = {"it": ["Maria", "Giulia", "Luca", "Marco"], "de": ["Anna", "Lena", "Jonas", "Felix"],
         "en": ["Emma", "Olivia", "James", "Harry"], "es": ["Lucía", "Sofía", "Javier", "Pablo"]}
LAST = {"it": ["Bianchi", "Ferrari", "Esposito", "Colombo"], "de": ["Müller", "Schmidt", "Weber", "Wagner"],
        "en": ["Smith", "Jones", "Taylor", "Brown"], "es": ["García", "López", "Martínez", "Sánchez"]}
REF = {"it": "v.r.", "de": "Ref.:", "en": "Ref.", "es": "V.R."}
UPTO = {"it": "fino a", "de": "bis", "en": "up to", "es": "hasta"}
ABOVE = {"it": "superiore a", "de": "über", "en": "above", "es": "superior a"}


def num(x, comma):
    """Sayıyı bir basamakla yazar; comma=True ise ondalık virgül kullanır."""
    s = f"{x:.1f}"
    return s.replace(".", ",") if comma else s


def messy_name(name, loinc):
    """Test adını laboratuvarların yazdığı gibi bozar."""
    r = random.random()
    if r < 0.15 and loinc in ABBR:
        name = ABBR[loinc]                               # sadece kısaltma
    elif r < 0.30 and loinc in ABBR:
        name = f"{name} ({ABBR[loinc]})"                 # ad + kısaltma
    elif r < 0.40 and " " in name:
        first, rest = name.split(" ", 1)
        name = f"{first[:6]}. {rest}"                    # kırpılmış ad
    if random.random() < 0.10:                           # OCR harf hatası
        for a, b in random.sample(OCR_SWAPS, len(OCR_SWAPS)):
            if a in name:
                name = name.replace(a, b, 1)
                break
    return name


def messy_unit(unit):
    """Birimi bazen küçük harfle ya da µ yerine u ile yazar."""
    if random.random() < 0.3:
        unit = unit.lower()
    if random.random() < 0.3:
        unit = unit.replace("µ", "u")
    return unit


def messy_range(low, high, lang, comma):
    """Referans aralığını farklı biçimlerde yazar."""
    a = num(low, comma) if has(low) else None
    b = num(high, comma) if has(high) else None
    if a and b:
        return random.choice([f"{a} - {b}", f"{a}-{b}", f"{a} – {b}"])
    if b:
        return random.choice([f"< {b}", f"<{b}", f"{UPTO[lang]} {b}"])
    return random.choice([f"> {a}", f">{a}", f"{ABOVE[lang]} {a}"])


def make_line(style, name, val, mark, unit, rng, lang):
    """Bir tahlil satırını seçilen laboratuvar stiline göre yazar."""
    if style == "classic":                   # temiz biçime en yakın stil
        return f"{name:<24}{val:>8} {unit:<9}({rng})"
    if style == "dots":                      # noktalı çizgi + yıldız
        dots = "." * max(3, 28 - len(name))
        star = " *" if mark else ""
        return f"{name} {dots} {val}{star} {unit}  {REF[lang]} {rng}"
    if style == "colon":                     # iki nokta + köşeli parantez
        tag = f" ({mark})" if mark else ""
        return f"{name}: {val} {unit}{tag} [{rng}]"
    return f"{name:<26}{val:>8} {mark or '':<2}{unit:<10}{rng}"   # columns: parantezsiz sütunlar


def make_messy_report(tests, lang):
    """Tek bir dağınık rapor ve doğru cevaplarını üretir."""
    style = random.choice(STYLES)
    comma = lang != "en" and random.random() < 0.7       # bazı laboratuvarlar nokta kullanır
    upper = random.random() < 0.3                        # bazı laboratuvarlar her şeyi BÜYÜK yazar
    patient = f"{random.choice(FIRST[lang])} {random.choice(LAST[lang])}"
    dob = f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(1940,2005)}"

    p_label, d_label = PATIENT[lang]
    lines = [TITLES[lang].upper() if upper else TITLES[lang],
             f"{p_label}: {patient}    {d_label}: {dob}", ""]
    truth = []
    for i, (_, t) in enumerate(tests.iterrows()):
        if i == 0:
            lines.append(f"--- {SECTIONS[lang][0]} ---")
        if i == 6:
            lines += ["", f"--- {SECTIONS[lang][1]} ---"]
        value = round(pick_value(t.low, t.high), 1)
        fl = flag(value, t.low, t.high)
        name = messy_name(t[f"name_{lang}"], t.loinc)
        if upper:
            name = name.upper()
        mark = fl if fl != "N" and random.random() < 0.7 else ""
        lines.append(make_line(style, name, num(value, comma), mark,
                               messy_unit(t.unit), messy_range(t.low, t.high, lang, comma), lang))
        truth.append({"loinc": t.loinc, "value": value, "unit": t.unit,
                      "low": to_json(t.low), "high": to_json(t.high), "flag": fl})
    lines += ["", "Pag. 1/1"]
    meta = {"style": style, "patient": {"name": patient, "dob": dob}}
    return "\n".join(lines), truth, meta


def main(n_per_lang=25):
    random.seed(43)                                      # temiz setten farklı tohum
    tests = pd.read_csv("data/tests.csv")
    out = Path("data/reports_messy")
    out.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        for i in range(1, n_per_lang + 1):
            text, truth, meta = make_messy_report(tests, lang)
            stem = f"{lang}_{i:03d}"
            (out / f"{stem}.txt").write_text(text, encoding="utf-8")
            (out / f"{stem}.json").write_text(
                json.dumps({"lang": lang, **meta, "results": truth}, ensure_ascii=False, indent=2),
                encoding="utf-8")
    print(f"{len(LANGS) * n_per_lang} dağınık rapor üretildi: {out}\n")
    print((out / "it_001.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
