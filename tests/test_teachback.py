"""Anlama kontrolü testleri: cevap anahtarı her durumda doğru mu?  python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from teachback import DIRECTION_OPTIONS, grade, log_result, make_questions  # noqa: E402


def fact(name, value, low, high, flag, level=None):
    return {"name": name, "value": value, "unit": "u", "low": low, "high": high,
            "range": f"{low} – {high}", "flag": flag,
            "level": level or {"L": "düşük", "H": "yüksek", "N": None}[flag]}


FACTS = {"a": fact("Hemoglobin", 9.0, 12.0, 16.0, "L"),       # en çok sapan (düşük)
         "b": fact("ALT", 45.0, None, 40.0, "H"),
         "c": fact("Demir", 90.0, 50.0, 170.0, "N"),
         "d": fact("TSH", 2.0, 0.4, 4.0, "N")}


def test_answer_is_always_an_option():
    for seed in range(50):
        for q in make_questions(FACTS, seed):
            assert q["answer"] in q["options"]
            assert len(set(q["options"])) == len(q["options"])


def test_find_question_points_to_most_deviating_value():
    for seed in range(50):
        q = make_questions(FACTS, seed)[0]
        assert q["answer"] == "Hemoglobin" and "altında" in q["question"]
        # çeldiriciler aynı yönde (düşük) olmamalı, yoksa iki doğru cevap olur
        assert all(FACTS[c]["flag"] != "L" for c in FACTS if FACTS[c]["name"] in q["options"]
                   and FACTS[c]["name"] != q["answer"])


def test_direction_question_matches_flag():
    for seed in range(50):
        q = [q for q in make_questions(FACTS, seed) if q["kind"] == "yön"][0]
        f = next(f for f in FACTS.values() if f["name"] in q["question"])
        assert q["answer"] == DIRECTION_OPTIONS[{"L": 0, "N": 1, "H": 2}[f["flag"]]]


def test_all_normal_report():
    facts = {"c": FACTS["c"], "d": FACTS["d"]}
    qs = make_questions(facts, 0)
    assert qs[0]["answer"] == "Bütün sonuçlarım referans aralığında."
    assert qs[-1]["kind"] == "eylem"


def test_grade_and_log(tmp_path):
    qs = make_questions(FACTS, 1)
    right = [q["answer"] for q in qs]
    assert grade(qs, right) == [True] * len(qs)
    assert grade(qs, [None] * len(qs)) == [False] * len(qs)
    log = tmp_path / "log.jsonl"
    log_result("r1", "m", qs, right, 1, path=log)
    assert '"score": 3' in log.read_text(encoding="utf-8")
