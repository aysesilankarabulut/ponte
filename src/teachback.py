"""Anlama kontrolü (teach-back): kullanıcı açıklamayı doğru anladı mı?

Sağlık iletişiminde "teach-back" yönteminde hasta, anlatılanı kendi sözleriyle tekrar eder.
Ponte bunun ölçülebilir, basit bir hâlini kullanır: açıklamadan sonra 3 çoktan seçmeli soru.
  1. Normal dışı değeri bulma   ("Hangi değeriniz referans aralığının üstünde?")
  2. Yönü anlama                ("X değeriniz ne durumda?")
  3. Ne yapacağını bilme        ("Bu sonuçlar için ne yapmalısınız?")
Soruları dil modeli değil KOD üretir; böylece cevap anahtarı her zaman doğrudur ve bekleme olmaz.
Cevaplar kişisel bilgi olmadan results/teachback/log.jsonl dosyasına yazılır (kullanıcı testi için).
"""
import hashlib
import json
import random
import time
from pathlib import Path

from doctor_questions import deviation
from verify import fmt

LOG = Path("results/teachback/log.jsonl")

DIRECTION_OPTIONS = ["Referans aralığının altında (düşük)",
                     "Referans aralığında (normal)",
                     "Referans aralığının üstünde (yüksek)"]
ACTION_OPTIONS = ["Sonuçlarımı doktorumla konuşmalıyım.",
                  "Kendi başıma ilaç kullanmaya başlamalıyım.",
                  "Hiçbir şey yapmama gerek yok."]


def _value_text(f):
    level = f.get("level") or "normal"
    return (f"{f['name']} değeriniz {fmt(f['value'])} {f['unit']}; referans aralığı {f['range']}. "
            f"Bu değer {level}.")


def make_questions(facts, seed=0):
    """Gerçeklerden (facts) 3 soru üretir. Her soru: soru, seçenekler, doğru cevap, açıklama."""
    rng = random.Random(seed)
    abnormal = sorted([c for c, f in facts.items() if f["flag"] != "N"],
                      key=lambda c: deviation(facts[c]), reverse=True)
    normal = [c for c, f in facts.items() if f["flag"] == "N"]
    questions = []

    # 1. Normal dışı değeri bulma: en çok sapan değer + aynı yönde olmayan 2 çeldirici
    if abnormal:
        top = facts[abnormal[0]]
        side = "altında" if top["flag"] == "L" else "üstünde"
        others = [c for c in normal + abnormal[1:] if facts[c]["flag"] != top["flag"]]
        if len(others) >= 2:
            distract = rng.sample(others, 2)
            options = [top["name"]] + [facts[c]["name"] for c in distract]
            rng.shuffle(options)
            questions.append({
                "kind": "bulma",
                "question": f"Aşağıdakilerden hangisi referans aralığının {side}?",
                "options": options, "answer": top["name"], "explain": _value_text(top)})
    else:
        questions.append({
            "kind": "bulma",
            "question": "Tahlil sonuçlarınızın genel durumu nedir?",
            "options": ["Bütün sonuçlarım referans aralığında.",
                        "Bazı sonuçlarım referans aralığının dışında."],
            "answer": "Bütün sonuçlarım referans aralığında.",
            "explain": "Okunan bütün değerleriniz referans aralığında."})

    # 2. Yönü anlama: ikinci en çok sapan değer (yoksa ilki); bazen bir normal değer
    pool = abnormal[1:2] or abnormal[:1]
    if normal and rng.random() < 0.3:
        pool = [rng.choice(normal)]
    if pool:
        f = facts[pool[0]]
        answer = DIRECTION_OPTIONS[{"L": 0, "N": 1, "H": 2}[f["flag"]]]
        questions.append({
            "kind": "yön",
            "question": f"{f['name']} değeriniz ne durumda?",
            "options": list(DIRECTION_OPTIONS), "answer": answer, "explain": _value_text(f)})

    # 3. Ne yapacağını bilme (her zaman)
    questions.append({
        "kind": "eylem",
        "question": "Bu sonuçlar için ne yapmalısınız?",
        "options": list(ACTION_OPTIONS), "answer": ACTION_OPTIONS[0],
        "explain": "Ponte teşhis koymaz ve tedavi önermez. Sonuçlarınızı mutlaka doktorunuzla konuşun."})
    return questions


def report_id(text):
    """Raporun kendisini kaydetmeden, aynı raporu tanımak için kısa bir parmak izi."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def grade(questions, answers):
    """Her soru için doğru mu? (cevap verilmemişse yanlış sayılır)."""
    return [a == q["answer"] for q, a in zip(questions, answers)]


def log_result(rid, model, questions, answers, attempt=1, path=LOG):
    """Sonucu kişisel bilgi olmadan kaydeder: zaman, rapor parmak izi, soru türleri, doğru/yanlış."""
    correct = grade(questions, answers)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "report": rid, "model": model,
                             "attempt": attempt,
                             "kinds": [q["kind"] for q in questions], "correct": correct,
                             "score": sum(correct)}, ensure_ascii=False) + "\n")
    return correct
