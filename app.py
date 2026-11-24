"""Ponte web arayüzü.

Çalıştırmak için (ponte klasöründe, sanal ortam açıkken):
    streamlit run app.py
Tarayıcıda http://localhost:8501 açılır. Ollama'nın açık olması gerekir.
"""
import os
import sys
import threading
import urllib.error
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)                                   # data/ ve results/ yolları buna göre
sys.path.insert(0, str(ROOT / "src"))

import pipeline as p                              # noqa: E402
from explain import DISCLAIMER                    # noqa: E402

st.set_page_config(page_title="Ponte", page_icon="🌉", layout="wide")


@st.cache_resource
def warm(model_name):
    """Sayfa açılınca modeli arka planda belleğe yükler; ilk istekte beklemeyi azaltır."""
    threading.Thread(target=p.warm_up, args=(model_name,), daemon=True).start()
    return True

STATUS_ICON = {"yüksek": "🔴 yüksek", "düşük": "🔵 düşük", "sınırda yüksek": "🟠 sınırda yüksek",
               "sınırda düşük": "🟠 sınırda düşük", "normal": "🟢 normal"}
EXAMPLES = [Path(f"data/reports_messy/{lang}_{i:03d}.txt")   # her dilden 3 sentetik rapor
            for lang in ["it", "de", "en", "es"] for i in (10, 11, 12)]


# ---------------------------------------------------------------- kenar çubuğu
with st.sidebar:
    st.header("Ayarlar")
    model = st.selectbox("Dil modeli", ["llama3.1:8b", "llama3.2:3b"],
                         help="8B daha doğru ama daha yavaş; 3B daha hızlı ama daha çok hata yapar.")
    example = st.selectbox("Örnek rapor (sentetik)", ["—"] + [e.stem for e in EXAMPLES],
                           help="Denemek için hazır bir rapor seçebilirsiniz. Hiçbiri gerçek hastaya ait değildir.")
    warm(model)
    st.divider()
    st.markdown("🔒 **Gizlilik:** Raporunuz bu bilgisayardan dışarı çıkmaz. "
                "Dil modeli yerel olarak (Ollama) çalışır, internet bağlantısı kullanılmaz.")
    st.markdown("🛡️ **Doğrulama:** Modelin yazdığı her cümle; sayı, düşük/yüksek yönü ve "
                "yasak içerik (teşhis, ilaç önerisi) açısından kod tarafından kontrol edilir.")
    st.caption(DISCLAIMER)

# ---------------------------------------------------------------- giriş
st.title("🌉 Ponte")
st.markdown("##### Yabancı dildeki kan tahlili raporunuzu sade Türkçeyle anlayın")
st.caption("İtalyanca, Almanca, İngilizce ve İspanyolca raporlar desteklenir.")

default_text = ""
if example != "—":
    default_text = Path(f"data/reports_messy/{example}.txt").read_text(encoding="utf-8")
uploaded = st.file_uploader("Rapor dosyası (.txt)", type=["txt"])
if uploaded is not None:
    default_text = uploaded.read().decode("utf-8", errors="replace")
text = st.text_area("Rapor metni", value=default_text, height=260,
                    placeholder="Tahlil raporunuzun metnini buraya yapıştırın…")

col_btn, col_info = st.columns([1, 3])
go = col_btn.button("Raporu açıkla", type="primary", disabled=not text.strip())
col_info.caption("⏱️ İşlem bu bilgisayarın gücüne göre birkaç dakika sürebilir "
                 "(8B modelle yaklaşık 5 dakika). Açıklama cümleleri yazıldıkça ekranda görünür.")

if go:
    st.session_state.pop("result", None)
    try:
        with st.status("Rapor işleniyor…", expanded=True) as status:
            lang = p.detect_lang(text)
            st.write(f"Rapor dili: **{p.LANG_NAMES_TR[lang]}**")
            st.write("1/3 · Tahlil değerleri okunuyor…")
            read = p.read_report(text, model, direct=True)
            if not read["rows"]:
                status.update(label="Raporda tanınan bir tahlil bulunamadı.", state="error")
                st.stop()
            st.write(f"✓ {len(read['rows'])} tahlil okundu ({read['seconds']:.0f} sn). "
                     f"Açıklama hazırlanırken değerlerinize göz atabilirsiniz:")
            preview = p.results_table(p.ex.build_facts(read["rows"], p.NAMES))
            preview["Durum"] = preview["Durum"].map(STATUS_ICON)
            st.dataframe(preview, hide_index=True)
            st.write("2/3 · Açıklama yazılıyor — her cümle doğrulandıktan sonra burada görünür:")
            live, shown, expl = st.empty(), [], None
            for kind, item in p.explain_stream(read["rows"], model):
                if kind == "cümle":
                    name = p.NAMES.get(item["fact"], {}).get("name_tr", "")
                    if item["problem"]:
                        shown.append(f"- ~~{item['text']}~~ ⛔ _{item['problem']}: reddedildi, "
                                     f"yerine güvenli cümle konacak_")
                    else:
                        shown.append(f"- **{name}:** {item['text']}")
                    live.markdown("\n".join(shown))
                else:
                    expl = item
            st.write(f"✓ Açıklama hazır ({expl['seconds']:.0f} sn)")
            st.write("3/3 · Doktorunuza sorabileceğiniz sorular hazırlanıyor…")
            ques = p.doctor_questions(expl["facts"], lang, model)
            st.write(f"✓ Sorular hazır ({ques['seconds']:.0f} sn)")
            status.update(label="Tamamlandı", state="complete", expanded=False)
        st.session_state["result"] = {"lang": lang, "read": read, "expl": expl, "ques": ques}
    except urllib.error.URLError:
        st.error("Dil modeline bağlanılamadı. Ollama açık mı? "
                 "Görev çubuğunda lama simgesi görünmüyorsa Ollama uygulamasını başlatın.")

# ---------------------------------------------------------------- sonuçlar
res = st.session_state.get("result")
if res:
    facts = res["expl"]["facts"]
    abnormal = [f for f in facts.values() if f["flag"] != "N"]
    urgent = [f["name"] for f in facts.values() if f.get("urgent")]

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Okunan tahlil", len(facts))
    m2.metric("Normal dışı", len(abnormal))
    m3.metric("Rapor dili", p.LANG_NAMES_TR[res["lang"]])
    m4.metric("Okunamayan satır", len(res["read"]["unread"]))

    if urgent:
        st.error(f"**Önemli:** {', '.join(urgent)} değeriniz referans aralığının üst sınırının iki "
                 f"katından fazla. Bu sonuçları doktorunuzla en kısa sürede konuşun.", icon="⚠️")
    if res["read"]["unread"]:
        with st.expander(f"⚠️ {len(res['read']['unread'])} satır okunamadı — lütfen kontrol edin"):
            st.caption("Bu satırlarda bir ölçü birimi var ama hiçbir tahlile bağlanamadı. "
                       "Önemli bir değer olabilir; raporunuzdan kendiniz kontrol edin.")
            for line in res["read"]["unread"]:
                st.code(line, language=None)

    tab1, tab2, tab3, tab4 = st.tabs(["💬 Açıklama", "📋 Sonuçlar", "❓ Doktora sorular", "🔍 Doğrulama"])

    with tab1:
        md = res["expl"]["markdown"].split("\n", 1)[1]          # baştaki başlığı at
        st.markdown(md)

    with tab2:
        table = p.results_table(facts)
        table["Durum"] = table["Durum"].map(STATUS_ICON)
        st.dataframe(table, hide_index=True)

    with tab3:
        lang_tr = p.LANG_NAMES_TR[res["lang"]]
        st.caption(f"Soruları Türkçe okuyun; doktorunuza {lang_tr} hallerini gösterebilirsiniz.")
        for i, q in enumerate(res["ques"]["final"], 1):
            c1, c2 = st.columns(2)
            c1.markdown(f"**{i}.** {q['tr']}")
            c2.markdown(f"_{q['doc']}_")
        export = "\n".join(f"{i}. {q['doc']}\n   ({q['tr']})"
                           for i, q in enumerate(res["ques"]["final"], 1))
        st.download_button("Soruları indir (.txt)", export, file_name="doktor_sorulari.txt")

    with tab4:
        e = res["expl"]
        n_model = len(e["accepted"]) + len(e["rejected"])
        st.markdown(f"- Modelin yazdığı cümle: **{n_model}**\n"
                    f"- Doğrulamadan geçen: **{len(e['accepted'])}**\n"
                    f"- Reddedilen: **{len(e['rejected'])}**\n"
                    f"- Kodun eklediği güvenli cümle: **{len(e['added'])}**\n"
                    f"- Reddedilen doktor sorusu: **{len(res['ques']['rejected'])}**")
        for r in e["rejected"]:
            st.warning(f"**{r['problem']}** — {r['text']}")
        for r in res["ques"]["rejected"]:
            st.warning(f"**{r['problem']}** — {r['tr']}")
        st.caption(f"Süreler: okuma {res['read']['seconds']:.0f} sn · açıklama {e['seconds']:.0f} sn · "
                   f"sorular {res['ques']['seconds']:.0f} sn · model: {model}")

    st.info(DISCLAIMER, icon="ℹ️")
