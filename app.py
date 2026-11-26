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

# Projenin kendi modülleri her çalıştırmada yeniden yüklensin: bir dosya değişince
# Streamlit'i kapatıp açmak gerekmez (Streamlit sadece app.py'yi kendisi yeniler).
for _f in (ROOT / "src").glob("*.py"):
    sys.modules.pop(_f.stem, None)

import pipeline as p                              # noqa: E402
import teachback as tb                            # noqa: E402
import ocr                                        # noqa: E402
import ui_style as ui                             # noqa: E402
from doctor_questions import deviation            # noqa: E402
from explain import DISCLAIMER, EMERGENCY_NOTE, SEX_NOTE  # noqa: E402

st.set_page_config(page_title="Ponte", page_icon="🌉", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(ui.CSS, unsafe_allow_html=True)


@st.cache_resource
def warm(model_name):
    """Sayfa açılınca modeli arka planda belleğe yükler; ilk istekte beklemeyi azaltır."""
    threading.Thread(target=p.warm_up, args=(model_name,), daemon=True).start()
    return True

STATUS_ICON = {"yüksek": "🔴 Yüksek", "düşük": "🔵 Düşük", "sınırda yüksek": "🟠 Sınırda yüksek",
               "sınırda düşük": "🟠 Sınırda düşük", "normal": "🟢 Normal"}


# ---------------------------------------------------------------- üst bölüm
st.markdown(ui.HERO_HTML, unsafe_allow_html=True)

# ---------------------------------------------------------------- rapor ekleme
EXAMPLES = {"İtalyanca": "it_010", "Almanca": "de_011", "İngilizce": "en_012", "İspanyolca": "es_010"}
st.session_state.setdefault("report_text", "")
st.session_state.setdefault("mode", None)
st.markdown(ui.tile_highlight(st.session_state["mode"]), unsafe_allow_html=True)


def take_file(name, data):
    """Yüklenen dosyayı / fotoğrafı metne çevirip metin kutusuna koyar."""
    try:
        with st.spinner("Rapor okunuyor…"):
            text_, warning = ocr.file_to_text(name, data)
    except RuntimeError:
        st.session_state["ocr_msg"] = ocr.status()[1]
        return
    except Exception as err:                       # okunamayan dosya, Tesseract hatası vb.
        st.session_state["ocr_msg"] = f"Dosya okunamadı ({type(err).__name__}: {err})"
        return
    if not text_.strip():
        st.session_state["ocr_msg"] = ("Fotoğrafta yazı bulunamadı. Raporu düz bir yere koyup, "
                                       "bütün sayfa görünecek şekilde ve ışık yansımadan tekrar çekin.")
        return
    st.session_state["report_text"] = text_
    st.session_state["ocr_msg"] = warning


with st.container(border=True):
    st.markdown("### Raporunuzu nasıl eklemek istersiniz?")
    c1, c2, c3 = st.columns(3)
    for col, (key, label, sub) in zip((c1, c2, c3), [
            ("camera", "📷  Fotoğraf çek", "Telefonun kamerasıyla"),
            ("file", "📄  Dosya yükle", "PDF, fotoğraf ya da metin"),
            ("paste", "📋  Metni yapıştır", "Kopyaladığınız rapor")]):
        if col.button(label, key=f"tile_{key}"):
            st.session_state["mode"] = key
            st.rerun()
        col.caption(sub)

    mode = st.session_state["mode"]
    if mode == "camera":
        ok, msg = ocr.status()
        if not ok:
            st.warning(msg)
        photo = st.file_uploader("Raporun fotoğrafını çekin ya da galeriden seçin",
                                 type=["jpg", "jpeg", "png", "webp"], key="photo",
                                 help="Telefonda bu düğme kamerayı açar. Raporu düz bir yere koyun, "
                                      "bütün sayfa görünsün ve ışık yansımasın.")
        shot = None
        if st.toggle("Bilgisayarın kamerasını kullan"):
            shot = st.camera_input("Raporu kameraya tutun", label_visibility="collapsed")
        for item in (photo, shot):
            if item is not None and st.session_state.get("last_file") != (item.name, item.size):
                st.session_state["last_file"] = (item.name, item.size)
                take_file(item.name if "." in item.name else "foto.jpg", item.getvalue())
    elif mode == "file":
        up = st.file_uploader("Rapor dosyası", type=["pdf", "txt", "jpg", "jpeg", "png", "webp"],
                              key="upload")
        if up is not None and st.session_state.get("last_file") != (up.name, up.size):
            st.session_state["last_file"] = (up.name, up.size)
            take_file(up.name, up.getvalue())

    ex_cols = st.columns([2.2, 1, 1, 1, 1])
    ex_cols[0].caption("Denemek için örnek rapor:")
    for col, (lang_name, stem) in zip(ex_cols[1:], EXAMPLES.items()):
        if col.button(lang_name, key=f"ex_{stem}"):
            st.session_state["report_text"] = Path(f"data/reports_messy/{stem}.txt").read_text(encoding="utf-8")
            st.session_state["mode"] = "paste"
            st.session_state["ocr_msg"] = ""
            st.rerun()

    if st.session_state.get("ocr_msg"):
        st.markdown(ui.note(ui.esc(st.session_state["ocr_msg"]), "ocr"), unsafe_allow_html=True)
    if mode or st.session_state["report_text"]:
        text = st.text_area("Rapor metni (gerekirse düzeltebilirsiniz)", key="report_text", height=220,
                            placeholder="Raporunuzun metnini buraya yapıştırın.")
    else:
        text = st.session_state["report_text"]
    go = st.button("Raporumu açıkla", type="primary", disabled=not text.strip())
    if not text.strip():
        st.caption("Düğme, rapor metni kutuya gelince açılır.")
    st.caption("İşlem yaklaşık 5 dakika sürer. Değerleriniz 2 dakika içinde görünür; "
               "açıklama cümleleri yazıldıkça eklenir.")

st.markdown(ui.TRUST_HTML, unsafe_allow_html=True)

with st.expander("Gelişmiş ayarlar"):
    model = st.selectbox("Dil modeli", ["llama3.1:8b", "llama3.2:3b"],
                         help="8B daha doğru ama daha yavaş; 3B daha hızlı ama çok daha fazla hata yapar.")
    st.caption("Uygulama, dil modelini Ollama ile bu bilgisayarda çalıştırır.")
warm(model)

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
        rid = tb.report_id(text)
        st.session_state["result"] = {"lang": lang, "read": read, "expl": expl, "ques": ques, "rid": rid,
                                      "teach": tb.make_questions(expl["facts"], seed=int(rid, 16) % 10_000)}
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
    n_ab = len(abnormal)
    summary = (f"{p.LANG_NAMES_TR[res['lang']]} raporunuzda <b>{len(facts)} tahlil</b> okundu; "
               + (f"<b>{n_ab} tanesi</b> referans aralığının dışında." if n_ab
                  else "hepsi referans aralığında."))
    st.markdown(f'<p class="ponte-summary">{summary}</p>', unsafe_allow_html=True)

    if urgent:
        st.markdown(ui.note(f"<b>Önemli:</b> {ui.esc(', '.join(urgent))} değeriniz referans aralığının üst "
                            f"sınırının iki katından fazla. Bu sonuçları doktorunuzla en kısa sürede "
                            f"konuşun.", "urgent"), unsafe_allow_html=True)
    if res["read"]["unread"]:
        with st.expander(f"{len(res['read']['unread'])} satır okunamadı. Lütfen raporunuzdan kontrol edin."):
            st.caption("Bu satırlarda bir tahlil sonucu var gibi görünüyor ama tahlilin adı, değeri ya da "
                       "referans aralığı tam okunamadı. Önemli bir değer olabilir.")
            for line in res["read"]["unread"]:
                st.code(line, language=None)

    tab1, tab_tb, tab2, tab3, tab4 = st.tabs(["💬 Açıklama", "✅ Anladım mı?", "📋 Sonuçlar",
                                             "❓ Doktora sorular", "🔍 Doğrulama"])

    with tab1:
        e = res["expl"]
        if abnormal:
            st.caption("Yeşil bant referans aralığını, renkli çizgi sizin değerinizi gösterir. "
                       "Aralıktan en çok uzaklaşan değerler en üsttedir.")
        order = sorted([c for c, f in facts.items() if f["flag"] != "N"],
                       key=lambda c: (not facts[c].get("urgent"), -deviation(facts[c])))
        for code in order:
            model_s = [x["text"] for x in e["accepted"] if x["fact"] == code]
            code_s = [x["text"] for x in e["added"] if x["fact"] == code]
            st.markdown(ui.result_card(facts[code], model_s + code_s, by_code=not model_s),
                        unsafe_allow_html=True)
        low = [f["name"] for f in facts.values() if f["flag"] == "L"]
        if low:
            st.markdown(ui.note(f"Referans aralığının altındaki değerleriniz ({ui.esc(', '.join(low))}) "
                                f"için doktorunuza danışmanız önerilir."), unsafe_allow_html=True)
        sex = [f["name"] for f in facts.values() if f["flag"] != "N" and f.get("sex_specific")]
        if sex:
            st.markdown(ui.note(f"{ui.esc(', '.join(sex))}: {SEX_NOTE}"), unsafe_allow_html=True)
        normal = [f["name"] for f in facts.values() if f["flag"] == "N"]
        if normal:
            with st.expander(f"Referans aralığında olan {len(normal)} sonucunuz"):
                st.write(", ".join(normal) + ".")
        if abnormal:
            st.markdown(ui.note(EMERGENCY_NOTE, "emergency"), unsafe_allow_html=True)
        st.caption("Açıklamayı okuduktan sonra **✅ Anladım mı?** sekmesinde 3 kısa soruyla "
                   "kendinizi kontrol edebilirsiniz.")

    with tab_tb:
        st.markdown("Açıklamayı doğru anladığınızdan emin olmak için 3 kısa soru. "
                    "Yanlış cevap verirseniz doğru bilgi tekrar gösterilir.")
        st.caption("Cevaplarınız projenin değerlendirmesi için kaydedilir; raporunuz ve kişisel "
                   "bilgileriniz kaydedilmez.")
        questions = res["teach"]
        with st.form(f"teachback_{res['rid']}"):
            answers = [st.radio(f"**{i}.** {q['question']}", q["options"], index=None,
                                key=f"tb_{res['rid']}_{i}") for i, q in enumerate(questions, 1)]
            sent = st.form_submit_button("Cevapları kontrol et", type="primary")
        if sent:
            if any(a is None for a in answers):
                st.warning("Lütfen bütün soruları cevaplayın.")
            else:
                key = f"tb_attempt_{res['rid']}"
                st.session_state[key] = st.session_state.get(key, 0) + 1
                correct = tb.log_result(res["rid"], model, questions, answers, st.session_state[key])
                for i, (q, ok) in enumerate(zip(questions, correct), 1):
                    if ok:
                        st.success(f"**{i}.** Doğru: {q['answer']}", icon="✅")
                    else:
                        st.error(f"**{i}.** Doğru cevap: **{q['answer']}**  \n{q['explain']}", icon="❌")
                score = sum(correct)
                if score == len(questions):
                    st.balloons()
                    st.markdown(f"### {score}/{len(questions)} — Açıklamayı çok iyi anlamışsınız!")
                else:
                    st.markdown(f"### {score}/{len(questions)}")
                    st.markdown("Kırmızı kutulardaki bilgileri okuyup **Açıklama** sekmesine bir kez "
                                "daha göz atın; isterseniz soruları tekrar cevaplayabilirsiniz.")

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

    st.markdown(ui.note(DISCLAIMER), unsafe_allow_html=True)

st.markdown(ui.FOOTER_HTML, unsafe_allow_html=True)
