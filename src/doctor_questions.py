"""Doktora köprü: hastanın doktoruna sorabileceği soruları iki dilde hazırlar.

  - Türkçe: hasta anlasın diye
  - Belgenin dili (İtalyanca, Almanca, İngilizce, İspanyolca): doktora gösterebilsin diye
Sorular iki gruptur:
  1. Tahlil soruları: referans aralığından EN ÇOK sapan 3 sonuç için (sapmayı kod hesaplar).
     Bu soruları dil modeli yazar; her soru verify.check_question ile kontrol edilir.
     Geçemeyen sorunun yerine kodun hazır sorusu konur.
  2. Genel sorular (tedavi/ilaç, beslenme/yaşam tarzı, tahlil tekrarı): her zaman kodun
     5 dilde hazır yazdığı sorular. Böylece bu üç konu hiçbir zaman eksik kalmaz.

Kullanım:
  python src/doctor_questions.py            → 4 rapor (her dilden 1), llama3.1:8b
Sonuçlar: results/questions/<model>/<rapor>.json ve okunabilir <rapor>.md
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from explain import build_facts
from generate_report import LANGS
from read_llm import OLLAMA_URL
from verify import check_question

LANG_NAMES = {"it": "Italian", "de": "German", "en": "English", "es": "Spanish"}
LANG_NAMES_TR = {"it": "İtalyanca", "de": "Almanca", "en": "İngilizce", "es": "İspanyolca"}
DIRECTION = {"tr": ("düşük", "yüksek"), "it": ("basso", "alto"), "de": ("zu niedrig", "zu hoch"),
             "en": ("low", "high"), "es": ("bajo", "alto")}
TEMPLATE_TEST = {
    "tr": "{name} değerimin {dir} çıkmasının sebebi ne olabilir?",
    "it": "Perché il mio valore di {name} è {dir}?",
    "de": "Warum ist mein Wert für {name} {dir}?",
    "en": "Why is my {name} {dir}?",
    "es": "¿Por qué mi valor de {name} está {dir}?",
}
TEMPLATE_GENERAL = {
    "tr": ["Bu sonuçlar için bir tedaviye ya da ilaca ihtiyacım var mı?",
           "Beslenmemde ya da yaşam tarzımda bir değişiklik yapmalı mıyım?",
           "Tahlili ne zaman tekrarlamalıyım?"],
    "it": ["Ho bisogno di una terapia o di farmaci per questi risultati?",
           "Devo cambiare qualcosa nella mia alimentazione o nel mio stile di vita?",
           "Quando devo ripetere gli esami?"],
    "de": ["Brauche ich wegen dieser Ergebnisse eine Behandlung oder Medikamente?",
           "Sollte ich meine Ernährung oder meinen Lebensstil ändern?",
           "Wann sollte ich die Untersuchung wiederholen?"],
    "en": ["Do I need any treatment or medication because of these results?",
           "Should I change my diet or lifestyle?",
           "When should I repeat the tests?"],
    "es": ["¿Necesito algún tratamiento o medicamento por estos resultados?",
           "¿Debo cambiar algo en mi alimentación o en mi estilo de vida?",
           "¿Cuándo debo repetir los análisis?"],
}

TOP_N = 3

INSTRUCTIONS = """You help a patient prepare questions for their doctor about their lab results.
You get some results that are outside the reference range, as JSON.
For EACH result write exactly ONE short question that the PATIENT asks the doctor about it.
Write it in two languages:
  "tr": Turkish (for the patient), use "name_tr";
  "doc": {doc_lang} (to show the doctor), use "name_doc".
Rules:
  - The patient is speaking: say "my value" ("değerim"), never "your value" ("değeriniz").
  - ONE sentence that ends with a question mark. Do not repeat the value as a statement.
  - Ask, never answer. Do not state a diagnosis and do not name any disease.
  - Say "low" or "high" exactly as given in "status". Use no numbers, or only the given value.
  - "fact": the code of the result.
Examples of good "tr" questions:
  "Hemoglobin değerimin düşük çıkmasının olası sebepleri nelerdir?"
  "LDL kolesterol değerimi düşürmek için neler yapabilirim?"
Answer in JSON."""


def answer_schema(codes):
    return {"type": "object", "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {"fact": {"type": "string", "enum": sorted(codes)},
                       "tr": {"type": "string"}, "doc": {"type": "string"}},
        "required": ["fact", "tr", "doc"]}}}, "required": ["questions"]}


def deviation(f):
    """Değer, aşılan sınırdan yüzde kaç uzakta? (normal değerler için 0)"""
    if f["flag"] == "L" and f["low"]:
        return (f["low"] - f["value"]) / f["low"]
    if f["flag"] == "H" and f["high"]:
        return (f["value"] - f["high"]) / f["high"]
    return 0.0


def top_abnormal(facts, n=TOP_N):
    """En çok sapan n normal dışı sonucun kodları (büyükten küçüğe)."""
    abnormal = [c for c, f in facts.items() if f["flag"] != "N"]
    return sorted(abnormal, key=lambda c: deviation(facts[c]), reverse=True)[:n]


def ask_model(model, facts, codes, doc_lang, doc_names):
    abnormal = {c: {"name_tr": facts[c]["name"], "name_doc": doc_names[c],
                    "value": facts[c]["value"], "unit": facts[c]["unit"],
                    "range": facts[c]["range"],
                    "status": "low" if facts[c]["flag"] == "L" else "high"}
                for c in codes}
    body = {"model": model, "stream": False, "format": answer_schema(abnormal.keys()),
            "messages": [{"role": "system",
                          "content": INSTRUCTIONS.format(doc_lang=LANG_NAMES[doc_lang])},
                         {"role": "user", "content": json.dumps(abnormal, ensure_ascii=False)}],
            "options": {"temperature": 0, "num_ctx": 4096}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as resp:
        return json.loads(resp.read())["message"]["content"]


def template_test_question(code, f, doc_lang, doc_names):
    i = 0 if f["flag"] == "L" else 1
    return {"fact": code, "by": "code",
            "tr": TEMPLATE_TEST["tr"].format(name=f["name"], dir=DIRECTION["tr"][i]),
            "doc": TEMPLATE_TEST[doc_lang].format(name=doc_names[code], dir=DIRECTION[doc_lang][i])}


def general_questions(doc_lang):
    return [{"fact": "GENERAL", "by": "code", "tr": tr, "doc": doc}
            for tr, doc in zip(TEMPLATE_GENERAL["tr"], TEMPLATE_GENERAL[doc_lang])]


def compose(accepted, facts, codes, doc_lang, doc_names):
    """Son liste: her seçilen tahlil için bir soru (modelinki ya da kodunki) + genel sorular."""
    final = []
    for code in codes:
        mine = [q for q in accepted if q["fact"] == code]
        final.append(mine[0] if mine else template_test_question(code, facts[code], doc_lang, doc_names))
    return final + general_questions(doc_lang)


def render(questions, doc_lang, n_abnormal):
    lines = ["# Doktorunuza sorabileceğiniz sorular", ""]
    n_test = sum(q["fact"] != "GENERAL" for q in questions)
    if n_abnormal > n_test:
        lines += [f"_Referans aralığı dışında {n_abnormal} sonucunuz var. İlk sorular, "
                  f"aralıktan en çok uzaklaşan {n_test} sonuç için hazırlandı._", ""]
    for i, q in enumerate(questions, 1):
        lines += [f"{i}. {q['tr']}", f"   _{LANG_NAMES_TR[doc_lang]}:_ {q['doc']}", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--n", type=int, default=1, help="dil başına rapor sayısı")
    ap.add_argument("--folder", default="data/reports_messy")
    args = ap.parse_args()

    names = pd.read_csv("data/names_tr.csv").set_index("loinc").to_dict("index")
    tests = pd.read_csv("data/tests.csv")
    out = Path("results") / "questions" / args.model.replace(":", "_").replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.model}  →  {out}\n")

    for lang in LANGS:
        doc_names = dict(zip(tests.loinc, tests[f"name_{lang}"]))
        for i in range(1, args.n + 1):
            stem = f"{lang}_{i:03d}"
            if (out / f"{stem}.json").exists():
                print(f"{stem}: zaten var, atlandı")
                continue
            gold = json.loads((Path(args.folder) / f"{stem}.json").read_text(encoding="utf-8"))
            facts = build_facts(gold["results"], names)
            codes = top_abnormal(facts)
            n_abnormal = sum(f["flag"] != "N" for f in facts.values())
            if not codes:
                print(f"{stem}: normal dışı sonuç yok, atlandı")
                continue
            start = time.time()
            try:
                raw = ask_model(args.model, facts, codes, lang, doc_names)
            except urllib.error.URLError:
                print("\nOllama'ya bağlanılamadı. Ollama açık mı?")
                return
            seconds = time.time() - start
            try:
                proposed = json.loads(raw)["questions"][:2 * len(codes)]
            except (ValueError, KeyError, TypeError):
                proposed = []
            accepted, rejected = [], []
            for q in proposed:
                problem = check_question(q, facts, lang)
                (rejected if problem else accepted).append({**q, "problem": problem} if problem else q)
            accepted = [q for q in accepted if q["fact"] in codes]
            final = compose(accepted, facts, codes, lang, doc_names)
            text = render(final, lang, n_abnormal)
            (out / f"{stem}.md").write_text(text, encoding="utf-8")
            (out / f"{stem}.json").write_text(json.dumps(
                {"model": args.model, "seconds": round(seconds, 1), "chosen": codes, "raw": raw,
                 "accepted": accepted, "rejected": rejected, "final": final},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"===== {stem}: {len(proposed)} soru, {len(rejected)} reddedildi, {seconds:.0f} sn")
            for r in rejected:
                print(f"  REDDEDİLDİ ({r['problem']}): {r['tr']}")
            print("\n" + text)


if __name__ == "__main__":
    main()
