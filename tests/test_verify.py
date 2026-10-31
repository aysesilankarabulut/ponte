"""Doğrulama katmanının testleri. Çalıştırmak için:  python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from verify import check_sentence, verify  # noqa: E402

FACTS = {
    "718-7": {"name": "Hemoglobin", "value": 10.2, "unit": "g/dL", "low": 12.0, "high": 16.0,
              "range": "12,0 – 16,0", "flag": "L"},
    "2093-3": {"name": "Total kolesterol", "value": 269.8, "unit": "mg/dL", "low": None,
               "high": 200.0, "range": "< 200,0", "flag": "H"},
    "2132-9": {"name": "B12 vitamini", "value": 465.6, "unit": "pg/mL", "low": 200.0,
               "high": 900.0, "range": "200,0 – 900,0", "flag": "N"},
}


def s(fact, text):
    return {"fact": fact, "text": text}


def test_correct_sentence_passes():
    assert check_sentence(s("718-7", "Hemoglobin değeriniz 10,2 g/dL, referans aralığı 12,0 – 16,0; yani düşük."), FACTS) is None


def test_wrong_number_is_caught():
    assert check_sentence(s("718-7", "Hemoglobin değeriniz 12,8 g/dL ve düşük."), FACTS) == "sayı hatası"


def test_wrong_direction_is_caught():
    assert check_sentence(s("718-7", "Hemoglobin değeriniz 10,2 g/dL ile yüksek."), FACTS) == "yön hatası"


def test_normal_called_high_is_caught():
    assert check_sentence(s("2132-9", "B12 vitamini değeriniz yüksek."), FACTS) == "yön hatası"


def test_numbers_inside_names_are_ignored():
    assert check_sentence(s("2132-9", "B12 vitamini sinir sistemi için önemlidir."), FACTS) is None


def test_diagnosis_is_caught():
    assert check_sentence(s("718-7", "Bu sonuç anemi olduğunuzu gösterir."), FACTS) == "yasak içerik"


def test_reassurance_is_caught():
    assert check_sentence(s("2093-3", "Kolesterolünüz biraz yüksek ama endişelenmeyin."), FACTS) == "yasak içerik"


def test_general_sentence_without_numbers_passes():
    assert check_sentence(s("GENERAL", "Sonuçlarınızı doktorunuzla konuşun."), FACTS) is None


def test_missing_abnormal_gets_code_sentence():
    accepted, rejected, added = verify([s("718-7", "Hemoglobin değeriniz düşük.")], FACTS)
    assert [a["fact"] for a in added] == ["2093-3"]
    assert "269,8" in added[0]["text"] and "üstünde" in added[0]["text"]


def test_value_equal_to_a_limit_is_still_caught():
    # gerçek değer 10,2; cümle değeri 12,0 diyor (alt sınırla aynı sayı)
    assert check_sentence(s("718-7", "Hemoglobin değeriniz 12,0 g/dL; aralık 12,0 – 16,0."), FACTS) == "sayı hatası"


def test_number_starting_with_10_is_not_mistaken_for_unit():
    facts = {"2132-9": {**FACTS["2132-9"], "value": 1061.3, "flag": "H"}}
    assert check_sentence(s("2132-9", "B12 vitamini değeriniz 1061,3 pg/mL ve yüksek."), facts) is None


def test_range_followed_by_unit_is_not_a_value_claim():
    # gerçek bir model cümlesi: aralığın üst sınırı birimle yazılmış
    text = "Hemoglobin değeri 10.2 g/dL'dir. Normal aralığı 12,0 – 16,0 g/dL'dir. Değeri düşük."
    assert check_sentence(s("718-7", text), FACTS) is None


def test_upper_limit_with_unit_is_not_a_value_claim():
    text = "Kolesterol değeri 269.8 mg/dL'dir. Normal aralığı < 200,0 mg/dL'dir. Değeri yüksek."
    assert check_sentence(s("2093-3", text), FACTS) is None


from verify import check_question  # noqa: E402


def q(fact, tr, doc):
    return {"fact": fact, "tr": tr, "doc": doc}


def test_good_question_passes():
    assert check_question(q("718-7", "Hemoglobin değerimin düşük olmasının sebebi ne olabilir?",
                            "Perché il mio valore di emoglobina è basso?"), FACTS, "it") is None


def test_medication_question_is_allowed():
    assert check_question(q("GENERAL", "İlaç kullanmam gerekir mi?", "Devo prendere dei farmaci?"), FACTS, "it") is None


def test_statement_is_not_a_question():
    assert check_question(q("GENERAL", "Demir ilacı almalısınız.", "Deve prendere ferro."), FACTS, "it") == "tr: soru değil"


def test_question_with_answer_is_caught():
    bad = q("GENERAL", "İlaç almalı mıyım? Evet, almalısınız.", "Devo prendere farmaci?")
    assert check_question(bad, FACTS, "it") is not None


def test_disease_name_in_doctor_language_is_caught():
    bad = q("718-7", "Hemoglobin değerim neden düşük?", "Ho l'anemia?")
    assert check_question(bad, FACTS, "it") == "doc: hastalık adı"


def test_wrong_direction_in_question_is_caught():
    bad = q("718-7", "Hemoglobin değerim neden yüksek?", "Perché la mia emoglobina è alta?")
    assert check_question(bad, FACTS, "it") == "tr: yön hatası"


def test_doctor_voice_is_caught():
    # gerçek model sorusu: hasta "seviyeniz" diyemez
    bad = q("718-7", "Hemoglobin seviyeniz neden bu kadar düşük?", "Warum ist Ihr Hämoglobinwert so niedrig?")
    assert check_question(bad, FACTS, "de") == "tr: yanlış kişi"


def test_polite_address_to_doctor_is_allowed():
    good = q("718-7", "Hemoglobin değerimin düşük olmasını açıklar mısınız?",
             "Können Sie mir erklären, warum mein Hämoglobin zu niedrig ist?")
    assert check_question(good, FACTS, "de") is None


def test_doctor_voice_in_doc_language_is_caught():
    bad = q("718-7", "Hemoglobin değerim neden düşük?", "Why is your hemoglobin low?")
    assert check_question(bad, FACTS, "en") == "doc: yanlış kişi"


def test_abnormal_called_normal_is_caught():
    # gerçek model cümlesi (es_002): düşük hemoglobine "normal" demiş
    text = "Hemoglobin tahlili, kırmızı kan hücrelerinde oksijen taşıyan proteinin ölçülmesidir. Değeri normal aralığındadır."
    assert check_sentence(s("718-7", text), FACTS) == "yön hatası"


def test_percent_from_range_is_not_a_normal_claim():
    text = "Hemoglobin değeriniz 10,2 g/dL ve normal aralığının altında, yani düşük."
    assert check_sentence(s("718-7", text), FACTS) is None
