"""Sentetik raporlardan 'telefon fotoğrafı' benzeri görüntüler üretir (fotoğraftan okuma deneyi için).

Her rapor farklı bir bozulmayla çizilir: hafif eğiklik, bulanıklık, kumlanma (gürültü),
kenarlara doğru gölge, düşük çözünürlük ve JPEG sıkıştırması. Tohum sabittir (tekrarlanabilir).

Kullanım:  python src/make_photos.py --src data/reports_final --out data/photos_final
"""
import argparse
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"]


def photo(text, rng, font):
    lines = text.splitlines()
    img = Image.new("L", (1500, 80 + 36 * len(lines)), rng.randint(235, 250))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((50, 40 + 36 * i), line, fill=rng.randint(15, 45), font=font)
    img = img.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=rng.randint(170, 210))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.3)))
    px = img.load()
    for _ in range(rng.randint(20000, 60000)):                 # kumlanma
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        px[x, y] = max(0, min(255, px[x, y] + rng.randint(-60, 60)))
    shade = rng.randint(4, 8)                                   # kenara doğru gölge
    grad = Image.linear_gradient("L").resize(img.size)
    if rng.random() < 0.5:
        grad = grad.rotate(90, expand=False)
    grad = grad.point(lambda v: 255 - v // shade)
    img = Image.composite(img, Image.new("L", img.size, 0), grad)
    scale = rng.uniform(0.62, 0.82)                             # telefon çözünürlüğü
    return img.resize((int(img.width * scale), int(img.height * scale))).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/reports_final")
    ap.add_argument("--out", default="data/photos_final")
    ap.add_argument("--seed", type=int, default=45)
    a = ap.parse_args()
    font = ImageFont.truetype(next(f for f in FONTS if os.path.exists(f)), 26)
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reports = sorted(Path(a.src).glob("*.txt"))
    for rp in reports:
        photo(rp.read_text(encoding="utf-8"), rng, font).save(out / f"{rp.stem}.jpg",
                                                              quality=rng.randint(60, 82))
    print(f"{len(reports)} fotoğraf üretildi: {out}")


if __name__ == "__main__":
    main()
