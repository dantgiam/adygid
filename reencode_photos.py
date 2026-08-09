"""Разовый пережим уже загруженных фотографий в WebP.

Правка в app/main.py:upload_photo действует только на новые загрузки, а в
хранилище уже лежат оригиналы по 5 МБ (кадры с телефона 4000×3000 как есть) и
PNG-миниатюры по 357 КБ. Скрипт скачивает каждое фото, ужимает до 1920 px,
сохраняет в WebP теми же параметрами, что и загрузчик, заливает новыми
объектами и переписывает ссылки в базе.

Старые файлы не удаляются: если что-то пойдёт не так, достаточно откатить
ссылки в базе. Запуск: python scratch/reencode_photos.py
"""
import io
import os
import sys

import httpx
import psycopg
from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_IMAGE_SIZE = (1920, 1920)
THUMB_SIZE = (480, 480)
WEBP_QUALITY = 82

DB_URL = os.environ["MIGRATE_DB_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
BUCKET = os.environ.get("SUPABASE_BUCKET", "uploads")
PUBLIC_PREFIX = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/"


def upload(client: httpx.Client, obj: str, data: bytes) -> str:
    r = client.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{obj}",
        content=data,
        headers={
            "Authorization": f"Bearer {SERVICE_KEY}",
            "apikey": SERVICE_KEY,
            "Content-Type": "image/webp",
            "x-upsert": "true",
        },
    )
    r.raise_for_status()
    return PUBLIC_PREFIX + obj


def encode(img: Image.Image, box) -> bytes:
    out = img.copy()
    out.thumbnail(box, Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def main() -> None:
    conn = psycopg.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("select id, url, thumb_url from photos where url like %s", (PUBLIC_PREFIX + "%",))
    rows = cur.fetchall()

    saved_before = saved_after = 0
    with httpx.Client(timeout=120) as client:
        for pid, url, thumb_url in rows:
            if url.endswith(".webp"):
                print(f"  #{pid} уже webp, пропускаю")
                continue
            src = client.get(url)
            src.raise_for_status()
            before = len(src.content)

            img = ImageOps.exif_transpose(Image.open(io.BytesIO(src.content)))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            name = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            big = encode(img, MAX_IMAGE_SIZE)
            small = encode(img, THUMB_SIZE)
            new_url = upload(client, f"{name}.webp", big)
            new_thumb = upload(client, f"{name}_thumb.webp", small)

            cur.execute(
                "update photos set url = %s, thumb_url = %s where id = %s",
                (new_url, new_thumb, pid),
            )
            conn.commit()
            saved_before += before
            saved_after += len(big)
            print(f"  #{pid} {before // 1024} КБ → {len(big) // 1024} КБ  ({name})")

    # Обложки статей и сценариев хранятся отдельными полями, а не в photos, и
    # это самостоятельные файлы — их тоже надо реально скачать и пережать, а не
    # просто переписать расширение на несуществующий объект. Сюда же попадает
    # плитка сценария, у которой миниатюры не было вовсе и на главную уходил
    # оригинал в 383 КБ: она создаётся здесь.
    with httpx.Client(timeout=120) as client:
        for table, col, thumb_col in (
            ("articles", "cover_url", "cover_thumb_url"),
            ("scenarios", "cover_url", "cover_thumb_url"),
            ("scenarios", "tile_cover_url", "tile_cover_thumb_url"),
        ):
            cur.execute(
                f"select id, {col} from {table} where {col} like %s and {col} not like %s",
                (PUBLIC_PREFIX + "%", "%.webp"),
            )
            for row_id, cover in cur.fetchall():
                src = client.get(cover)
                src.raise_for_status()
                before = len(src.content)
                img = ImageOps.exif_transpose(Image.open(io.BytesIO(src.content)))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                name = cover.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                big, small = encode(img, MAX_IMAGE_SIZE), encode(img, THUMB_SIZE)
                new_url = upload(client, f"{name}.webp", big)
                new_thumb = upload(client, f"{name}_thumb.webp", small)
                cur.execute(
                    f"update {table} set {col} = %s, {thumb_col} = %s where id = %s",
                    (new_url, new_thumb, row_id),
                )
                conn.commit()
                print(f"  {table}#{row_id} {col}: {before // 1024} КБ → {len(big) // 1024} КБ "
                      f"(превью {len(small) // 1024} КБ)")

    conn.close()
    print(f"\nФото в photos: {saved_before / 1048576:.1f} МБ → {saved_after / 1048576:.1f} МБ")


if __name__ == "__main__":
    main()
