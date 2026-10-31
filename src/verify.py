"""Doğrulama katmanı: dil modelinin yazdığı her açıklama cümlesini kontrol eder.

Her cümle bir tahlile ("fact") bağlıdır ya da genel bir cümledir ("GENERAL").
Bir cümle şu durumlarda REDDEDİLİR:
  1. Sayı hatası:   cümlede, bağlı olduğu tahlilin değeri / alt sınırı / üst sınırı dışında
                    bir sayı geçiyorsa (genel cümlelerde hiç sayı olmamalı).
  2. Yön hatası:    cümle "düşük" diyor ama değer yüksekse (ya da tersi), ya da normal bir
                    değere "düşük/yüksek" diyorsa.
  3. Yasak içerik:  teşhis koyuyor, ilaç/tedavi öneriyor ya da "endişelenmeyin" gibi
                    sonucu küçümsüyorsa.
Reddedilen cümle atılır. Normal dışı bir tahlil hakkında geçerli tek cümle kalmazsa,
kod o tahlil için kendi güvenli cümlesini yazar (kapsam kontrolü).
"""
import re

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Test adlarının ve birimlerin içindeki rakamlar sayı sayılmasın
NAME_NUMBER_RE = re.compile(r"(B12|T4|25-OH|HbA1c|A1c|(?<![\d,.])10\^[36]|(?<![\d,.])10[³⁶])", re.IGNORECASE)

LOW_WORDS = ["düşük", "altında", "azal", "eksik"]
HIGH_WORDS = ["yüksek", "üstünde", "üzerinde", "aşıyor", "artmış"]
FORBIDDEN = [
    "teşhis", "tanınız", "tanı kon", "hastasısınız", "hastalığınız", "kanser", "lösemi",
    "diyabet", "şeker hastası", "anemi", "ilaç", "tedavi", "takviye", "almalısınız",
    "almanız gerek", "kullanmalısınız", "endişelenmeyin", "endişe etmeyin", "önemli değil",
    "tehlikeli değil", "ciddi bir durum yok", "merak etmeyin",
]


def tr_lower(text):
    """Türkçe küçük harf: 'I' → 'ı', 'İ' → 'i'."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def numbers_in(text, fact=None):
    """Cümledeki sayıları bulur; test adı ve birim içindeki rakamları yok sayar."""
    if fact:
        text = text.replace(fact["unit"], " ")
    text = NAME_NUMBER_RE.sub(" ", text)
    return [float(n.replace(",", ".")) for n in NUMBER_RE.findall(text)]


def stated_values(text, unit):
    """Cümlede birimin hemen yanında yazan sayılar: '10,2 g/dL' → 10.2, '%6,9' → 6.9.
    Bu sayılar 'değeriniz şu' iddiasıdır; referans sınırlarına denk gelseler bile
    gerçek değere eşit olmak zorundadır. Bir aralığın parçası olan sayılar
    ('12,0 – 16,0 g/dL', '< 40 U/L') değer iddiası sayılmaz."""
    num = r"(\d+(?:[.,]\d+)?)"
    range_before = r"(?<![-–<>]\s)(?<![-–<>])"      # önünde aralık işareti olmasın
    found = re.findall(range_before + r"(?<![\d.,])" + num + r"\s*" + re.escape(unit), text, re.IGNORECASE)
    if unit == "%":
        found += re.findall(r"%\s*" + num, text)
    return [float(n.replace(",", ".")) for n in found]


# "Değeri normal aralığındadır" gibi "normal" iddiaları. "aralığından %20 yüksek" yakalanmaz.
NORMAL_RE = re.compile(r"(normal|referans) (aralı(ğı|k)(nda|ta)|sınırlar(ı içinde|da))([dt][ıiuü]r)?\b"
                       r"|\bnormaldir\b|\bnormal (düzeyde|seviyede|değerde)\b")


def claims_normal(text):
    return NORMAL_RE.search(tr_lower(text)) is not None


def claimed_direction(text):
    """Cümlenin iddia ettiği yön: 'L', 'H', 'BOTH' ya da None."""
    t = tr_lower(text)
    low = any(w in t for w in LOW_WORDS)
    high = any(w in t for w in HIGH_WORDS)
    if low and high:
        return "BOTH"
    return "L" if low else "H" if high else None


def check_sentence(sentence, facts):
    """Bir cümleyi kontrol eder. Sorun yoksa None, varsa sorunun adını döndürür."""
    text, ref = sentence["text"], sentence["fact"]
    t = tr_lower(text)
    if any(w in t for w in FORBIDDEN):
        return "yasak içerik"
    if ref == "GENERAL":
        if numbers_in(text):
            return "sayı hatası"
        if claimed_direction(text):
            return "yön hatası"
        return None
    fact = facts.get(ref)
    if fact is None:
        return "bilinmeyen tahlil"
    allowed = {x for x in (fact["value"], fact["low"], fact["high"]) if x is not None}
    if any(all(abs(n - a) > 1e-6 for a in allowed) for n in numbers_in(text, fact)):
        return "sayı hatası"
    if any(abs(n - fact["value"]) > 1e-6 for n in stated_values(text, fact["unit"])):
        return "sayı hatası"          # birimin yanındaki sayı, değerin kendisi olmalı
    claim = claimed_direction(text)
    if claim == "BOTH" or (claim and claim != fact["flag"]):
        return "yön hatası"
    if fact["flag"] != "N" and claims_normal(text):
        return "yön hatası"          # normal dışı bir değere "normal" demek: en tehlikeli hata
    return None


def fallback_sentence(fact):
    """Kodun kendi yazdığı güvenli cümle (model geçerli bir cümle yazamadığında)."""
    direction = "altında" if fact["flag"] == "L" else "üstünde"
    return (f"{fact['name']} değeriniz {fmt(fact['value'])} {fact['unit']}; "
            f"bu, referans aralığının ({fact['range']}) {direction}.")


def fmt(x):
    return f"{x:.1f}".replace(".", ",")


def verify(sentences, facts):
    """Bütün cümleleri kontrol eder; kabul edilenleri, reddedilenleri ve eklenenleri döndürür."""
    accepted, rejected = [], []
    for s in sentences:
        problem = check_sentence(s, facts)
        (rejected if problem else accepted).append({**s, "problem": problem} if problem else s)
    added = []
    for code, fact in facts.items():
        if fact["flag"] == "N":
            continue
        covered = any(s["fact"] == code and claimed_direction(s["text"]) == fact["flag"]
                      for s in accepted)
        if not covered:
            added.append({"fact": code, "text": fallback_sentence(fact), "by": "code"})
    return accepted, rejected, added


# ---------------------------------------------------------------------------
# Doktora sorulacak sorular için kontroller
# Sorularda "ilaç", "tedavi", "beslenme" gibi kelimeler serbesttir: doktora sormak güvenlidir.
# Ama soru bir iddiada bulunamaz, cevap veremez ve hastalık adı geçiremez.
# ---------------------------------------------------------------------------
DISEASES = {
    "tr": ["kanser", "tümör", "lösemi", "diyabet", "şeker hastalığı", "anemi"],
    "it": ["cancro", "tumore", "leucemia", "diabete", "anemia"],
    "de": ["krebs", "tumor", "leukämie", "diabetes", "anämie"],
    "en": ["cancer", "tumor", "tumour", "leukemia", "leukaemia", "diabetes", "anemia", "anaemia"],
    "es": ["cáncer", "tumor", "leucemia", "diabetes", "anemia"],
}


# Soruyu hasta soruyor: "değerim" olmalı, "değeriniz" değil.
# Türkçede "-niz" iyelik eki yakalanır; doktora hitap eden "misiniz", "önerirsiniz" serbesttir.
SECOND_PERSON_TR = re.compile(r"[aeıioöuü]n[ıiuü]z")
POLITE_TR = re.compile(r"s[ıiuü]n[ıiuü]z")
SECOND_PERSON_DOC = {
    "en": r"\byour\b",
    "de": r"\b(ihr|ihre|ihren|ihrem|ihrer|ihres|dein|deine)\b",
    "it": r"\b(suo|sua|suoi|sue|tuo|tua|tuoi|tue)\b",
    "es": r"\b(tu|tus)\b",
}


def wrong_person(text, lang):
    """Soru hastanın ağzından değil de doktorun ağzından mı yazılmış?"""
    if lang == "tr":
        return any(SECOND_PERSON_TR.search(w) and not POLITE_TR.search(w)
                   for w in re.findall(r"\w+", tr_lower(text)))
    return re.search(SECOND_PERSON_DOC[lang], text.lower()) is not None


def check_question(question, facts, doc_lang):
    """Hem Türkçe ('tr') hem belge dilindeki ('doc') soruyu kontrol eder."""
    ref = question["fact"]
    fact = facts.get(ref)
    if ref != "GENERAL" and fact is None:
        return "bilinmeyen tahlil"
    for side, lang in (("tr", "tr"), ("doc", doc_lang)):
        text = question[side].strip()
        if not text.endswith("?"):
            return f"{side}: soru değil"
        if re.search(r"[.!?]\s", text[:-1]):
            return f"{side}: birden fazla cümle"
        lower = tr_lower(text) if lang == "tr" else text.lower()
        if any(w in lower for w in DISEASES[lang]):
            return f"{side}: hastalık adı"
        if wrong_person(text, lang):
            return f"{side}: yanlış kişi"
        allowed = set() if fact is None else {x for x in (fact["value"], fact["low"], fact["high"]) if x is not None}
        if any(all(abs(n - a) > 1e-6 for a in allowed) for n in numbers_in(text, fact)):
            return f"{side}: sayı hatası"
    claim = claimed_direction(question["tr"])
    if claim and (fact is None or claim != fact["flag"]):
        return "tr: yön hatası"
    return None
