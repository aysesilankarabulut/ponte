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
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from generate_report import LANGS
from read_llm import OLLAMA_URL
from verify import fmt, verify

DISCLAIMER = ("Bu açıklama yalnızca belgeyi anlamanıza yardımcı olmak içindir; "
              "teşhis ya da tedavi önerisi değildir. Sonuçlarınızı mutlaka doktorunuzla konuşun.")


def range_text(low, high):
    if low is not None and high is not None:
        return f"{fmt(low)} – {fmt(high)}"
    return f"< {fmt(high)}" if high is not None else f"> {fmt(low)}"


def build_facts(results, names):
    """Okunan satırları, modele ve doğrulayıcıya verilecek 'gerçekler' listesine çevirir."""
    facts = {}
    for r in results:
        n = names[r["loinc"]]
        facts[r["loinc"]] = {"name": n["name_tr"], "what": n["what_tr"], "value": r["value"],
                             "unit": r["unit"], "low": r["low"], "high": r["high"],
                             "range": range_text(r["low"], r["high"]), "flag": r["flag"]}
    return facts


INSTRUCTIONS = """Sen, laboratuvar sonuçlarını hastalara sade Türkçeyle açıklayan bir yardımcısın.
Sana normal aralığın dışındaki sonuçlar JSON olarak verilecek. Her sonuç için 1 ya da 2 kısa cümle yaz:
  - tahlilin ne olduğunu verilen "what" bilgisiyle basitçe anlat,
  - değerin referans aralığına göre düşük mü yüksek mi olduğunu söyle.
Kurallar:
  - Sadece verilen sayıları, aynen yaz. Başka sayı yazma, hesap yapma.
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


def ask_model(model, facts):
    abnormal = {c: {k: f[k] for k in ("name", "what", "value", "unit", "range")} |
                {"durum": "düşük" if f["flag"] == "L" else "yüksek"}
                for c, f in facts.items() if f["flag"] != "N"}
    body = {"model": model, "stream": False, "format": answer_schema(abnormal.keys()),
            "messages": [{"role": "system", "content": INSTRUCTIONS},
                         {"role": "user", "content": json.dumps(abnormal, ensure_ascii=False)}],
            "options": {"temperature": 0, "num_ctx": 4096}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as resp:
        return json.loads(resp.read())["message"]["content"]


def render(facts, accepted, added):
    """Kullanıcıya gösterilecek metni kurar: önce normal dışılar, sonra normaller, en son uyarı."""
    lines = ["# Tahlil sonuçlarınızın açıklaması", ""]
    for code, f in facts.items():
        if f["flag"] == "N":
            continue
        mine = [s["text"] for s in accepted + added if s["fact"] == code]
        lines.append(f"**{f['name']}:** " + " ".join(mine))
        lines.append("")
    normal = [f["name"] for f in facts.values() if f["flag"] == "N"]
    if normal:
        lines += ["Referans aralığında olan sonuçlarınız: " + ", ".join(normal) + ".", ""]
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
            try:
                sentences = json.loads(raw)["sentences"]
            except (ValueError, KeyError, TypeError):
                sentences = []
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
