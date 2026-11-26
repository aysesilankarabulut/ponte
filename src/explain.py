"""Açıklama: okunan tahlil sonuçlarını sade Türkçeyle açıklar ve her cümleyi doğrular.

İş bölümü:
  - Kod: hangi değerin düşük/yüksek olduğunu hesaplar, normal sonuçların özet cümlesini yazar.
  - Dil modeli: sadece normal dışı değerler için kısa, sade cümleler yazar.
  - Doğrulama (verify.py): her cümlenin sayılarını, yönünü ve içeriğini kontrol eder.

Kullanım:
  python src/explain.py                      → 4 rapor (her dilden 1), llama3.1:8b
  python src/explain.py --n 2 --model llama3.2:3b
  python src/explain.py --reverify          → modeli çağırmadan, kayıtlı cevapları güncel
                                              doğrulayıcıyla yeniden kontrol eder
Sonuçlar: results/explanations/<model>/<rapor>.json ve okunabilir <rapor>.md
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from generate_report import LANGS
from read_llm import OLLAMA_URL
from verify import fmt, verify

SEX_NOTE = ("Bu tahlillerin referans aralığı kadın ve erkekte farklı olabilir; "
            "sonuçlarınızı doktorunuzla birlikte değerlendirin.")
EMERGENCY_NOTE = ("Şikâyetlerinize bilinç bulanıklığı gibi acil bir belirti eşlik ediyorsa "
                  "beklemeden acil servise başvurun.")
DISCLAIMER = ("Bu açıklama yalnızca belgeyi anlamanıza yardımcı olmak içindir; "
              "teşhis ya da tedavi önerisi değildir. Sonuçlarınızı mutlaka doktorunuzla konuşun.")


def range_text(low, high):
    if low is not None and high is not None:
        return f"{fmt(low)} – {fmt(high)}"
    return f"< {fmt(high)}" if high is not None else f"> {fmt(low)}"


def load_notes(path="data/clinical_notes.csv"):
    """Uzman değerlendirmesinden gelen klinik notlar: sınırda kategoriler ve cinsiyete bağlı aralıklar."""
    if not Path(path).exists():
        return {}
    notes = pd.read_csv(path, dtype={"loinc": str}).set_index("loinc")
    return {c: {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}
            for c, row in notes.iterrows()}


NOTES = load_notes()
URGENT_FACTOR = 2.0       # değer, üst sınırın en az 2 katıysa: "doktorunuza en kısa sürede danışın"


def level_of(value, flag, note):
    """'düşük', 'yüksek', 'sınırda düşük' ya da 'sınırda yüksek' (normal değerler için None)."""
    if flag == "N":
        return None
    if flag == "H":
        b = note.get("borderline_high_below")
        return "sınırda yüksek" if b is not None and value < b else "yüksek"
    b = note.get("borderline_low_from")
    return "sınırda düşük" if b is not None and value >= b else "düşük"


def build_facts(results, names, notes=None):
    """Okunan satırları, modele ve doğrulayıcıya verilecek 'gerçekler' listesine çevirir."""
    notes = NOTES if notes is None else notes
    facts = {}
    for r in results:
        n = names[r["loinc"]]
        note = notes.get(r["loinc"], {})
        facts[r["loinc"]] = {"name": n["name_tr"], "what": n["what_tr"], "value": r["value"],
                             "unit": r["unit"], "low": r["low"], "high": r["high"],
                             "range": range_text(r["low"], r["high"]), "flag": r["flag"],
                             "level": level_of(r["value"], r["flag"], note),
                             "sex_specific": bool(note.get("sex_specific")),
                             "urgent": bool(r["flag"] == "H" and r["high"]
                                            and r["value"] >= URGENT_FACTOR * r["high"])}
    return facts


INSTRUCTIONS = """Sen, laboratuvar sonuçlarını hastalara sade Türkçeyle açıklayan bir yardımcısın.
Sana normal aralığın dışındaki sonuçlar JSON olarak verilecek. Bu sonuçların HİÇBİRİ normal değildir.
Her sonuç için 1 ya da 2 kısa cümle yaz:
  - tahlilin ne olduğunu verilen "what" bilgisiyle basitçe anlat,
  - "durum" alanındaki ifadeyi ("düşük", "yüksek", "sınırda düşük" ya da "sınırda yüksek") cümlede aynen kullan.
Örnekler (düşük ve yüksek için ifadeler farklıdır):
  "Hemoglobin, kırmızı kan hücrelerinde oksijen taşıyan proteindir. Değeriniz 10,2 g/dL ile referans aralığının (12,0 – 16,0) altında, yani düşük."
  "ALT, karaciğer hakkında bilgi veren bir enzimdir. Değeriniz 58,4 U/L ile referans aralığının (< 40,0) üstünde, yani yüksek."
  "Trigliserit, kanda dolaşan temel yağ türüdür. Değeriniz 183,4 mg/dL ile referans aralığının (< 150,0) üstünde, yani sınırda yüksek."
Kurallar:
  - Hiçbir sonuca "normal" deme.
  - Sadece verilen sayıları, aynen yaz. Başka sayı yazma, yüzde ya da fark hesaplama.
  - Teşhis koyma, hastalık adı verme, ilaç ya da tedavi önerme.
  - Sonucu küçümseme ("endişelenmeyin" gibi) ya da büyütme.
  - Her cümlenin "fact" alanına ilgili sonucun kodunu yaz.
Cevabı JSON olarak ver."""


def answer_schema(codes):
    return {"type": "object", "properties": {"sentences": {"type": "array", "items": {
        "type": "object",
        "properties": {"fact": {"type": "string", "enum": sorted(codes) + ["GENERAL"]},
                       "text": {"type": "string"}},
        "required": ["fact", "text"]}}}, "required": ["sentences"]}


def request_body(model, facts, stream=False):
    """Modele gidecek isteği kurar: sadece normal dışı sonuçlar ve durumları."""
    abnormal = {c: {k: f[k] for k in ("name", "what", "value", "unit", "range")} |
                {"durum": f.get("level") or ("düşük" if f["flag"] == "L" else "yüksek")}
                for c, f in facts.items() if f["flag"] != "N"}
    return {"model": model, "stream": stream, "keep_alive": "30m", "format": answer_schema(abnormal.keys()),
            "messages": [{"role": "system", "content": INSTRUCTIONS},
                         {"role": "user", "content": json.dumps(abnormal, ensure_ascii=False)}],
            "options": {"temperature": 0, "num_ctx": 4096,
                        # cevap uzunluğu sınırı: küçük modeller bazen aynı cümleyi döngüde tekrarlar
                        "num_predict": 120 * len(abnormal) + 100}}


OBJECT_RE = re.compile(r"\{[^{}]*\}")


def parse_sentences(raw):
    """Modelin cevabından cümleleri çıkarır. Cevap yarıda kesilmişse (uzunluk sınırı),
    tamamlanmış cümleleri yine de kurtarır; aynı cümlenin tekrarlarını atar."""
    try:
        sentences = json.loads(raw)["sentences"]
    except (ValueError, KeyError, TypeError):
        sentences = []
        for obj in OBJECT_RE.findall(raw[raw.find("["):] if "[" in raw else ""):
            try:
                s = json.loads(obj)
            except ValueError:
                continue
            if isinstance(s, dict) and "fact" in s and "text" in s:
                sentences.append(s)
    out, seen = [], set()
    for s in sentences:
        key = (s.get("fact"), s.get("text"))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def ask_model(model, facts):
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(request_body(model, facts)).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as resp:
        return json.loads(resp.read())["message"]["content"]


def stream_model(model, facts):
    """Modelin cevabını parça parça verir (yazdıkça). Her parça bir metin parçasıdır."""
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(request_body(model, facts, True)).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as resp:
        for line in resp:
            if line.strip():
                chunk = json.loads(line)
                yield chunk.get("message", {}).get("content", "")
                if chunk.get("done"):
                    break


def render(facts, accepted, added):
    """Kullanıcıya gösterilecek metni kurar: önce normal dışılar, sonra normaller, en son uyarı."""
    lines = ["# Tahlil sonuçlarınızın açıklaması", ""]
    urgent = [f["name"] for f in facts.values() if f.get("urgent")]
    if urgent:
        lines += [f"> **Önemli:** {', '.join(urgent)} değeriniz referans aralığının üst sınırının "
                  f"iki katından fazla. Bu sonuçları doktorunuzla en kısa sürede konuşun.", ""]
    for code, f in facts.items():
        if f["flag"] == "N":
            continue
        mine = [s["text"] for s in accepted + added if s["fact"] == code]
        label = f["name"]
        if not any(s["fact"] == code for s in accepted) and f.get("what"):
            label += f" ({f['what']})"     # modelin cümlesi yoksa tahlilin ne olduğunu kod söyler
        lines.append(f"**{label}:** " + " ".join(mine))
        lines.append("")
    low = [f["name"] for f in facts.values() if f["flag"] == "L"]
    if low:   # uzman önerisi: ne kadar düşük olursa olsun doktora danışılmalı
        lines += [f"**Referans aralığının altındaki değerleriniz** ({', '.join(low)}) için "
                  f"doktorunuza danışmanız önerilir.", ""]
    sex = [f["name"] for f in facts.values() if f["flag"] != "N" and f.get("sex_specific")]
    if sex:
        lines += [f"_{', '.join(sex)}: {SEX_NOTE}_", ""]
    normal = [f["name"] for f in facts.values() if f["flag"] == "N"]
    if normal:
        lines += ["Referans aralığında olan sonuçlarınız: " + ", ".join(normal) + ".", ""]
    if any(f["flag"] != "N" for f in facts.values()):
        lines += [f"**{EMERGENCY_NOTE}**", ""]
    lines += [f"_{DISCLAIMER}_"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--n", type=int, default=1, help="dil başına rapor sayısı")
    ap.add_argument("--folder", default="data/reports_messy")
    ap.add_argument("--reverify", action="store_true")
    args = ap.parse_args()

    names = pd.read_csv("data/names_tr.csv").set_index("loinc").to_dict("index")
    out = Path("results") / "explanations" / args.model.replace(":", "_").replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Model: {args.model}  →  {out}\n")

    for lang in LANGS:
        for i in range(1, args.n + 1):
            stem = f"{lang}_{i:03d}"
            saved = out / f"{stem}.json"
            if saved.exists() and not args.reverify:
                print(f"{stem}: zaten var, atlandı")
                continue
            if args.reverify:
                if not saved.exists():
                    continue
                old = json.loads(saved.read_text(encoding="utf-8"))
                facts, raw, seconds = old["facts"], old["raw"], old["seconds"]
            else:
                gold = json.loads((Path(args.folder) / f"{stem}.json").read_text(encoding="utf-8"))
                facts = build_facts(gold["results"], names)
                start = time.time()
                try:
                    raw = ask_model(args.model, facts)
                except urllib.error.URLError:
                    print("\nOllama'ya bağlanılamadı. Ollama açık mı?")
                    return
                seconds = time.time() - start
            sentences = parse_sentences(raw)
            accepted, rejected, added = verify(sentences, facts)
            text = render(facts, accepted, added)
            (out / f"{stem}.md").write_text(text, encoding="utf-8")
            (out / f"{stem}.json").write_text(json.dumps(
                {"model": args.model, "seconds": round(seconds, 1), "facts": facts, "raw": raw,
                 "accepted": accepted, "rejected": rejected, "added": added},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"===== {stem}: {len(sentences)} cümle, {len(rejected)} reddedildi, "
                  f"{len(added)} cümleyi kod ekledi, {seconds:.0f} sn")
            for r in rejected:
                print(f"  REDDEDİLDİ ({r['problem']}): {r['text']}")
            print("\n" + text + "\n")


if __name__ == "__main__":
    main()
