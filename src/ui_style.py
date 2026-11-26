"""Ponte arayüzünün görsel parçaları ("Göl ve gün batımı" tasarımı).

Fikir: Lago Maggiore'de gölden gün batımına geçen renkler; üstte soluk bir köprü.
  Göl mavisi (#1B4965 → #2E6F95), gün batımı turuncusu (#F4A259), açık zemin (#F6FAFB).
  Durum renkleri anlam taşır: yüksek → mercan kırmızısı · düşük → mavi · sınırda → kehribar · normal → yeşil.
Yazı tipleri (Lora, DM Sans) uygulamanın içinde gelir (static/fonts); internetten yüklenmez.
"""
import html

INK = "#16324F"
MUTED = "#4B6378"
LAKE = "#1B4965"
LAKE2 = "#2E6F95"
SUNSET = "#F4A259"
LINE = "#DCE6EC"
STATUS = {             # (renk, açık zemin, etiket)
    "yüksek": ("#D9480F", "#FDE7DF", "Yüksek"),
    "düşük": ("#2F6FB3", "#E3EEF9", "Düşük"),
    "sınırda yüksek": ("#B7791F", "#FCF1DA", "Sınırda yüksek"),
    "sınırda düşük": ("#B7791F", "#FCF1DA", "Sınırda düşük"),
    "normal": ("#2E8B57", "#E5F4EA", "Normal"),
}

CSS = f"""
<style>
  @font-face {{ font-family: "Lora"; src: url("app/static/fonts/Lora.ttf") format("truetype");
               font-weight: 400 700; font-display: swap; }}
  @font-face {{ font-family: "DM Sans"; src: url("app/static/fonts/DMSans.ttf") format("truetype");
               font-weight: 100 1000; font-display: swap; }}

  html, body, .stApp, p, li, label, input, textarea, button, .stMarkdown, .stCaption {{
    font-family: "DM Sans", "Segoe UI", system-ui, sans-serif; }}
  /* Streamlit'in simgeleri (ok işaretleri vb.) kendi simge yazı tipinde kalsın */
  [data-testid="stIconMaterial"], [data-testid="stIconMaterial"] *, .material-symbols-rounded,
  [class*="material-symbols"], [data-testid="stExpanderToggleIcon"] {{
    font-family: "Material Symbols Rounded" !important; font-feature-settings: "liga" !important; }}
  h1, h2, h3, h1 *, h2 *, h3 *, .ponte-serif,
  [data-testid="stHeadingWithActionElements"], [data-testid="stHeadingWithActionElements"] * {{
    font-family: "Lora", Georgia, serif !important; color: {INK}; }}
  [data-testid="stHeadingWithActionElements"] a {{ display: none; }}   /* başlık yanındaki bağlantı simgesi */
  .stApp {{ background: #F6FAFB; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
  .block-container {{ padding-top: 0 !important; max-width: 860px; }}
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], section.main {{
    overflow-x: hidden; }}

  /* ---------- üst bölüm: göl ve gün batımı ---------- */
  .ponte-hero {{ position: relative; width: 100vw; margin-left: calc(50% - 50vw);
    background: linear-gradient(180deg, {LAKE} 0%, {LAKE2} 58%, #E9A46B 118%);
    color: #fff; padding: 2.6rem 1.25rem 5.5rem; overflow: hidden; }}
  .ponte-hero:after {{ content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 4.5rem;
    background: linear-gradient(180deg, rgba(246,250,251,0), #F6FAFB); }}
  .ponte-hero svg {{ position: absolute; right: -1rem; bottom: 2rem; width: min(440px, 70vw);
    color: rgba(255,255,255,.33); }}
  .ponte-hin {{ position: relative; z-index: 2; max-width: 820px; margin: 0 auto; }}
  .ponte-logo {{ font-family: "Lora", Georgia, serif; font-weight: 700; font-size: 1.6rem;
    color: #FFD8A8; letter-spacing: .02em; }}
  .ponte-hero h1 {{ color: #fff !important; font-size: clamp(1.9rem, 5vw, 2.7rem); line-height: 1.15;
    margin: .8rem 0 .6rem; padding: 0; font-weight: 700; }}
  .ponte-lead {{ font-size: 1.1rem; opacity: .93; max-width: 36rem; margin: 0; }}
  .ponte-langs {{ display: flex; flex-wrap: wrap; gap: .45rem; margin-top: 1rem; }}
  .ponte-langs span {{ background: rgba(255,255,255,.16); padding: .3rem .75rem; border-radius: 999px;
    font-size: .88rem; }}
  .ponte-langs b {{ font-weight: 700; margin-right: .3rem; opacity: .8; }}
  .ponte-langs .to {{ background: none; padding: .3rem .1rem; }}

  /* ---------- beyaz giriş kartı ---------- */
  [data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border: none !important;
    border-radius: 22px; box-shadow: 0 12px 30px rgba(27,73,101,.14); }}
  .ponte-overlap {{ height: 0; margin-top: -3.6rem; }}

  /* üç büyük seçenek */
  .st-key-tile_camera, .st-key-tile_file, .st-key-tile_paste,
  .st-key-tile_camera .stButton, .st-key-tile_file .stButton, .st-key-tile_paste .stButton {{ width: 100%; }}
  .st-key-tile_camera button, .st-key-tile_file button, .st-key-tile_paste button {{
    width: 100%; min-height: 6.2rem; border: none; border-radius: 18px; justify-content: flex-start;
    text-align: left; padding: 1rem 1.1rem; font-size: 1.12rem; font-weight: 700;
    transition: transform .12s ease; }}
  .st-key-tile_camera button p, .st-key-tile_file button p, .st-key-tile_paste button p {{
    font-size: 1.12rem; font-weight: 700; }}
  .st-key-tile_camera button {{ background: {SUNSET}; color: #3B1F00; }}
  .st-key-tile_file button {{ background: #E3F1F7; color: {LAKE}; }}
  .st-key-tile_paste button {{ background: #E9F5EC; color: #1E5B3A; }}
  .st-key-tile_camera button:hover, .st-key-tile_file button:hover, .st-key-tile_paste button:hover {{
    transform: translateY(-2px); }}
  .st-key-tile_camera button:focus-visible, .st-key-tile_file button:focus-visible,
  .st-key-tile_paste button:focus-visible {{ outline: 3px solid {INK}; outline-offset: 2px; }}

  /* örnek rapor bağlantıları */
  [class*="st-key-ex_"] button {{ background: none !important; border: none !important; padding: 0 .2rem;
    min-height: 0; color: {LAKE2} !important; text-decoration: underline; font-weight: 600; }}
  [class*="st-key-ex_"] button p {{ font-size: .92rem; }}

  /* ana düğme */
  .stButton > button[kind="primary"], [data-testid="stBaseButton-primary"],
  [data-testid="stFormSubmitButton"] button {{
    background: {LAKE2}; border: none; border-radius: 14px; font-size: 1.08rem; font-weight: 700;
    padding: .7rem 1.8rem; color: #fff; }}
  .stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{ background: {LAKE}; }}
  .stButton > button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled {{
    background: #C9D6DE; color: #5B6B79; cursor: not-allowed; }}

  /* güven satırı */
  .ponte-trust {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.6rem 0 .6rem; }}
  .ponte-trust div {{ display: flex; flex-direction: column; gap: .15rem; }}
  .ponte-trust i {{ font-style: normal; font-size: 1.4rem; }}
  .ponte-trust b {{ color: {INK}; font-size: 1rem; }}
  .ponte-trust span {{ color: {MUTED}; font-size: .88rem; line-height: 1.45; }}

  .ponte-summary {{ font-size: 1.18rem; color: {INK}; margin: .4rem 0 .9rem; }}

  /* ---------- sonuç kartları ---------- */
  .ponte-card {{ background: #fff; border-radius: 18px; border-left: 7px solid; padding: 1rem 1.15rem 1.05rem;
    margin: 0 0 .95rem; box-shadow: 0 6px 18px rgba(22,50,79,.08); }}
  .ponte-card-head {{ display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }}
  .ponte-name {{ font-weight: 700; font-size: 1.1rem; color: {INK}; }}
  .ponte-chip {{ font-size: .8rem; font-weight: 700; padding: .12rem .65rem; border-radius: 999px; }}
  .ponte-value {{ margin-left: auto; font-weight: 700; color: {INK}; font-variant-numeric: tabular-nums; }}
  .ponte-value small {{ color: {MUTED}; font-weight: 400; font-size: .82rem; }}
  .ponte-text {{ color: {INK}; line-height: 1.6; margin: .5rem 0 0; }}
  .ponte-code {{ color: {MUTED}; font-size: .8rem; margin-top: .35rem; }}
  .ponte-bar {{ position: relative; height: 36px; margin: .75rem 0 .1rem; }}
  .ponte-track {{ position: absolute; top: 12px; left: 0; right: 0; height: 10px; background: #EDF2F4;
    border-radius: 5px; }}
  .ponte-band {{ position: absolute; top: 12px; height: 10px; background: #8FD3A8; border-radius: 5px; }}
  .ponte-mark {{ position: absolute; top: 5px; width: 6px; height: 24px; border-radius: 3px;
    transform: translateX(-3px); box-shadow: 0 0 0 2px #fff; }}
  .ponte-edge {{ position: absolute; top: 5px; font-size: 15px; font-weight: 700; }}
  .ponte-lim {{ position: absolute; top: 25px; font-size: .72rem; color: #6B7F8E; transform: translateX(-50%);
    white-space: nowrap; }}

  .ponte-note {{ border-radius: 14px; padding: .8rem 1rem; margin: .6rem 0; line-height: 1.55; }}
  .ponte-note.urgent {{ background: #FDE7DF; color: #7A2A08; border: 1px solid #F5BFA8; }}
  .ponte-note.emergency {{ background: #FFF4EC; color: #7A2A08; border: 1px dashed #EDA97F; }}
  .ponte-note.info {{ background: #EEF5F8; color: {INK}; }}
  .ponte-note.ocr {{ background: #FFF4E5; color: #6B3A00; border: 1px solid #F6D2A2; }}

  .ponte-footer {{ color: {MUTED}; font-size: .8rem; margin-top: 2.5rem; padding-top: .8rem;
    border-top: 1px solid {LINE}; }}

  /* sekmeler */
  .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}

  @media (max-width: 640px) {{
    .ponte-trust {{ grid-template-columns: 1fr; }}
    .ponte-hero {{ padding: 2rem 1rem 5rem; }}
    .block-container {{ padding-left: .8rem !important; padding-right: .8rem !important; }}
    .ponte-value {{ margin-left: 0; width: 100%; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""

BRIDGE_SVG = """<svg viewBox="0 0 240 70" aria-hidden="true"><path d="M10 60 Q120 -10 230 60" fill="none"
stroke="currentColor" stroke-width="4"/><line x1="5" y1="60" x2="235" y2="60" stroke="currentColor"
stroke-width="4"/><g stroke="currentColor" stroke-width="2.5"><line x1="50" y1="60" x2="50" y2="33"/>
<line x1="85" y1="60" x2="85" y2="20"/><line x1="120" y1="60" x2="120" y2="16"/>
<line x1="155" y1="60" x2="155" y2="20"/><line x1="190" y1="60" x2="190" y2="33"/></g></svg>"""

HERO_HTML = f"""<div class="ponte-hero">{BRIDGE_SVG}<div class="ponte-hin">
<div class="ponte-logo">Ponte</div>
<h1>Yabancı dildeki tahlil raporunuzu Türkçe anlayın.</h1>
<p class="ponte-lead">Raporunuzun fotoğrafını çekin; değerlerinizi okuyup sade Türkçeyle açıklayalım.</p>
<div class="ponte-langs"><span><b>IT</b>İtalyanca</span><span><b>DE</b>Almanca</span><span><b>EN</b>İngilizce</span>
<span><b>ES</b>İspanyolca</span><span class="to">→</span><span><b>TR</b>Türkçe</span></div>
</div></div><div class="ponte-overlap"></div>"""

TRUST_HTML = """<div class="ponte-trust">
<div><i>🔒</i><b>Bilgisayarınızda kalır</b><span>Raporunuz internete gönderilmez; dil modeli bu bilgisayarda çalışır.</span></div>
<div><i>✔️</i><b>Her cümle kontrol edilir</b><span>Sayısı ya da yönü yanlış olan açıklama size gösterilmez.</span></div>
<div><i>🩺</i><b>Teşhis koymaz</b><span>Sonuçlarınızı anlamanıza yardım eder; kararı doktorunuzla verirsiniz.</span></div>
</div>"""

FOOTER_HTML = ('<div class="ponte-footer">Ponte, KTO Karatay Üniversitesi bitirme projesi (2026). '
               'Açıklamalar bu bilgisayarda çalışan bir dil modeliyle yazılır ve kodla doğrulanır.</div>')


def esc(text):
    return html.escape(str(text))


def fmt(x):
    return f"{x:.1f}".replace(".", ",")


def status_of(f):
    return f.get("level") or "normal"


def chip(level):
    color, bg, label = STATUS[level]
    return f'<span class="ponte-chip" style="color:{color};background:{bg}">{label}</span>'


def range_bar(f):
    """Değerin referans aralığına göre yerini gösteren çubuk (HTML)."""
    low, high, value = f["low"], f["high"], f["value"]
    color = STATUS[status_of(f)][0]
    if low is not None and high is not None:
        span = high - low or 1.0
        lo, hi = max(0.0, low - 0.6 * span), high + 0.6 * span
        band = (low, high)
    elif high is not None:                       # "< 200": tek üst sınır
        lo, hi = 0.0, high * 1.8
        band = (0.0, high)
    elif low is not None:                        # "> 40": tek alt sınır
        lo, hi = 0.0, low * 2.2
        band = (low, hi)
    else:
        return ""

    def pos(x):
        return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))

    parts = ['<div class="ponte-bar"><div class="ponte-track"></div>',
             f'<div class="ponte-band" style="left:{pos(band[0]):.1f}%;width:{pos(band[1]) - pos(band[0]):.1f}%"></div>']
    for lim in (low, high):
        if lim is not None:
            parts.append(f'<div class="ponte-lim" style="left:{pos(lim):.1f}%">{fmt(lim)}</div>')
    if value > hi:
        parts.append(f'<div class="ponte-edge" style="right:-2px;color:{color}">▶</div>')
    elif value < lo:
        parts.append(f'<div class="ponte-edge" style="left:-2px;color:{color}">◀</div>')
    else:
        parts.append(f'<div class="ponte-mark" style="left:{pos(value):.1f}%;background:{color}"></div>')
    parts.append("</div>")
    return "".join(parts)


def result_card(f, sentences, by_code=False):
    """Bir normal dışı sonuç: ad, durum, değer, aralık çubuğu ve açıklama cümleleri."""
    level = status_of(f)
    color = STATUS[level][0]
    text = " ".join(esc(s) for s in sentences)
    note_html = ('<div class="ponte-code">Bu açıklamayı uygulamanın kendisi yazdı '
                 '(dil modelinin cümlesi doğrulamadan geçemedi).</div>') if by_code else ""
    return (f'<div class="ponte-card" style="border-left-color:{color}">'
            f'<div class="ponte-card-head"><span class="ponte-name">{esc(f["name"])}</span>{chip(level)}'
            f'<span class="ponte-value">{fmt(f["value"])} {esc(f["unit"])} '
            f'<small>(referans {esc(f["range"])})</small></span></div>{range_bar(f)}'
            f'<p class="ponte-text">{text}</p>{note_html}</div>')


def note(text, kind="info"):
    return f'<div class="ponte-note {kind}">{text}</div>'


def tile_highlight(mode):
    """Seçili büyük düğmeyi belirginleştiren küçük CSS parçası."""
    if not mode:
        return ""
    return (f"<style>.st-key-tile_{mode} button {{ box-shadow: 0 0 0 3px {INK}; }}</style>")
