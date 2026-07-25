"""Разовый скрипт — вырезает стикеры по их реальным контурам (альфа-канал),
а не по ровной сетке — в исходнике стикеры не идеально выровнены по клеткам,
из-за чего наивная нарезка 5x5 резала их криво и цепляла соседей.

Запуск: docker compose exec api python slice_stickers.py
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

SRC = Path("site_app/static/stickers.png")
OUT_DIR = Path("site_app/static/stickers")
GRID = 5
PAD = 3
MIN_AREA = 400


def run():
    img = Image.open(SRC).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    mask = alpha > 15
    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5)))
    labels, count = ndimage.label(mask)
    objects = ndimage.find_objects(labels)

    blobs = []  # [y0, y1, x0, x1, area]
    for i, sl in enumerate(objects, start=1):
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        area = (labels[sl] == i).sum()
        if area < MIN_AREA:
            continue
        blobs.append([y0, y1, x0, x1, area])

    BIG_AREA = 3000
    big = [b for b in blobs if b[4] >= BIG_AREA]
    small = [b for b in blobs if b[4] < BIG_AREA]
    print(f"Крупных фрагментов: {len(big)}, мелких (довесков вроде звёзд): {len(small)}")

    def center(b):
        return ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2)

    # Каждый мелкий довесок приклеиваем к ближайшему крупному фрагменту —
    # так отдельно висящие звёзды/детали возвращаются к своему стикеру.
    for sb in small:
        scy, scx = center(sb)
        nearest = min(big, key=lambda bb: (center(bb)[0] - scy) ** 2 + (center(bb)[1] - scx) ** 2)
        nearest[0] = min(nearest[0], sb[0]); nearest[1] = max(nearest[1], sb[1])
        nearest[2] = min(nearest[2], sb[2]); nearest[3] = max(nearest[3], sb[3])

    print(f"Итоговых стикеров: {len(big)} (ожидалось {GRID*GRID})")

    # Реальные ряды могут быть неровными — группируем по 5 подряд после
    # сортировки по вертикали, а не по номинальной сетке.
    big.sort(key=lambda b: center(b)[0])
    numbered = []
    for i in range(0, len(big), GRID):
        row_group = sorted(big[i:i + GRID], key=lambda b: center(b)[1])
        numbered.extend(row_group)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("sticker-*.png"):
        old.unlink()

    for n, (y0, y1, x0, x1, _area) in enumerate(numbered, start=1):
        y0p, x0p = max(0, y0 - PAD), max(0, x0 - PAD)
        y1p, x1p = min(h, y1 + PAD), min(w, x1 + PAD)
        cell_img = img.crop((x0p, y0p, x1p, y1p))
        cell_img.save(OUT_DIR / f"sticker-{n:02d}.png")

    print(f"Готово: {len(numbered)} стикеров в {OUT_DIR}")


if __name__ == "__main__":
    run()
