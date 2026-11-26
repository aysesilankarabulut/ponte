"""Fotoğraf ve PDF'ten metin çıkarma (OCR).

- Fotoğraf (telefon kamerası ya da dosya): Tesseract OCR, dört dil birlikte (ita+deu+eng+spa).
- PDF: önce içindeki metin okunur (pypdf). Taranmış (resim) PDF'lerde metin yoksa kullanıcıya
  sayfanın fotoğrafını çekmesi önerilir.
Tesseract bu bilgisayarda çalışır; görüntü hiçbir yere gönderilmez.
OCR hataları (ör. 'Co1esterol', 'HCMOGLOBINA') karma okuyucunun zaten alıştığı türden hatalardır:
sentetik dağınık raporlar bu hatalarla üretildi ve ad/birim onarımı bunları düzeltir.
"""
import io
import os
import shutil

LANGS = "ita+deu+eng+spa"
# Dil dosyaları proje içinde (tessdata/) gelir; Tesseract kurulumunda dil seçmek gerekmez.
TESSDATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tessdata")


if os.path.isdir(TESSDATA):
    # Klasör yolunu tırnakla komuta eklemek Windows'ta sorun çıkarabiliyor; ortam değişkeni güvenli.
    os.environ["TESSDATA_PREFIX"] = TESSDATA


def _config(extra=""):
    return extra
WINDOWS_PATHS = [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]


def _tesseract():
    """pytesseract modülünü hazırlar; Tesseract kurulu değilse None döndürür."""
    try:
        import pytesseract
    except ImportError:
        return None
    if not shutil.which("tesseract"):
        for path in WINDOWS_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return None
    return pytesseract


def status():
    """OCR kullanılabilir mi? (hazır mı, eksik diller, kullanıcıya gösterilecek mesaj)"""
    t = _tesseract()
    if t is None:
        return False, ("Fotoğraf okuma için Tesseract OCR kurulu değil. Kurulum adımları için "
                       "README dosyasına bakın; bu sırada raporun metnini yapıştırabilirsiniz.")
    missing = [l for l in LANGS.split("+") if l not in t.get_languages(config=_config())]
    if missing:
        return False, f"Tesseract kurulu ama şu dil paketleri eksik: {', '.join(missing)}."
    return True, ""


def prepare(image):
    """Telefon fotoğrafını OCR için hazırlar: yönünü düzeltir, griye çevirir, küçükse büyütür."""
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image).convert("L")
    if image.width < 1600:
        scale = 1600 / image.width
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    return ImageOps.autocontrast(image)


def image_to_text(data):
    """Fotoğraf baytlarından metin (satır yapısı korunur)."""
    from PIL import Image
    t = _tesseract()
    if t is None:
        raise RuntimeError("Tesseract OCR kurulu değil.")
    image = prepare(Image.open(io.BytesIO(data)))
    # --psm 4 ("sütunlu metin"): noktalı satırlarda ('Hemoglobin ....... 12,9') değeri noktalardan
    # ayırır. --psm 6'ya göre geliştirme fotoğraflarında noktalı biçim %71,5 → %95,0.
    return t.image_to_string(image, lang=LANGS, config=_config("--psm 4"))


def pdf_to_text(data):
    """PDF'in içindeki metin. Taranmış PDF'lerde boş döner."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def file_to_text(name, data):
    """Yüklenen dosyayı türüne göre metne çevirir: (metin, uyarı)."""
    ext = name.lower().rsplit(".", 1)[-1]
    if ext == "txt":
        return data.decode("utf-8", errors="replace"), ""
    if ext == "pdf":
        text = pdf_to_text(data)
        if not text:
            return "", ("Bu PDF taranmış bir görüntü, içinde metin yok. Lütfen sayfanın fotoğrafını "
                        "çekip yükleyin.")
        return text, ""
    return clean(image_to_text(data)), "Metin fotoğraftan okundu. Analizden önce değerleri raporunuzla karşılaştırın."


def clean(text):
    """Fotoğraftan okunan metindeki sık OCR birim hatalarını düzeltir.
    Ör. '10%6/4L' → '10^6/µL', '10"3/pL' → '10^3/µL', 'mg/d1' → 'mg/dl'."""
    import re
    text = re.sub(r"\b10\s*(?:[^\s\d/]{1,2}|7)?\s*([36])\s*/\s*[^\s/]{0,2}?[lL]\b", r"10^\1/µL", text)
    text = re.sub(r"\b10\s*[79]\s*([36])\s*/\s*[µuplLI1|y4]{1,2}\b", r"10^\1/µL", text)  # '1093/11' gibi
    text = re.sub(r"/\s*d[1I|]\b", "/dl", text)
    text = re.sub(r"\bm[1I|]U/[lL]\b", "mIU/L", text)
    text = text.replace("—", "-").replace("–", "-")
    return text
