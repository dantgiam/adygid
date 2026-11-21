"""Фото заявок на досуг.

Те же правила, что у загрузки в админке (app/main.py): jpg/png/webp, не больше
8 МБ, кадр приводится к WebP, учитывается поворот телефона, есть миниатюра.
Если заданы SUPABASE_URL и SUPABASE_SERVICE_KEY — файл кладётся в тот же
публичный бакет. Иначе — в static/uploads/leisure/, его уже отдаёт /static.
Чужой формат и неразобранный файл не сохраняем.
"""
from __future__ import annotations

import io
import os
import re
import uuid

import httpx
from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_FILES = 8
MIN_WIDTH = 1200
THUMB_SIZE = (800, 800)
MAX_IMAGE_SIZE = (1920, 1920)
WEBP_QUALITY = 82

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(_ROOT, "static", "uploads", "leisure")
LOCAL_PREFIX = "/static/uploads/leisure/"
_NAME_RE = re.compile(r"[a-f0-9]+(?:_thumb)?\.webp$")


class PhotoError(Exception):
    def __init__(self, message: str):
        self.message = message


def supabase_ready() -> bool:
    return bool(os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_SERVICE_KEY", "").strip())


def _ext(file: UploadFile) -> str:
    name = (file.filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ext not in ALLOWED_EXT and ctype not in ALLOWED_TYPES:
        raise PhotoError("Разрешены только фото jpg, png или webp")
    if ctype and ctype not in ALLOWED_TYPES and ctype != "application/octet-stream":
        raise PhotoError("Разрешены только фото jpg, png или webp")
    return ext


def prepare_image(data: bytes) -> tuple[bytes, bytes]:
    if not data:
        raise PhotoError("Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoError("Файл больше 8 МБ")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise PhotoError("Файл не похож на фотографию") from exc
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if img.width < MIN_WIDTH:
        raise PhotoError(f"Ширина фото {img.width} px. Нужно не меньше {MIN_WIDTH} px")
    img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)
    orig = io.BytesIO()
    img.save(orig, "WEBP", quality=WEBP_QUALITY, method=6)
    thumb = img.copy()
    thumb.thumbnail(THUMB_SIZE)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, "WEBP", quality=WEBP_QUALITY, method=6)
    return orig.getvalue(), thumb_buf.getvalue()


def _public_base() -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    bucket = os.getenv("SUPABASE_BUCKET", "uploads")
    return f"{base}/storage/v1/object/public/{bucket}/"


async def _put_supabase(object_path: str, data: bytes) -> None:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    bucket = os.getenv("SUPABASE_BUCKET", "uploads")
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "image/webp",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base}/storage/v1/object/{bucket}/{object_path}",
            content=data,
            headers=headers,
        )
    if resp.status_code >= 400:
        raise PhotoError("Не удалось сохранить фото")


def _put_local(name: str, data: bytes) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return LOCAL_PREFIX + name


async def save_upload(file: UploadFile) -> dict:
    _ext(file)
    data = await file.read()
    orig, thumb = prepare_image(data)
    stem = uuid.uuid4().hex
    orig_name = f"leisure/{stem}.webp" if supabase_ready() else f"{stem}.webp"
    thumb_name = f"leisure/{stem}_thumb.webp" if supabase_ready() else f"{stem}_thumb.webp"
    if supabase_ready():
        await _put_supabase(orig_name, orig)
        await _put_supabase(thumb_name, thumb)
        base = _public_base()
        return {"url": base + orig_name, "thumb_url": base + thumb_name}
    return {"url": _put_local(orig_name, orig), "thumb_url": _put_local(thumb_name, thumb)}


def forget(url: str | None) -> None:
    """Удалить локальный файл, если запись в базу не удалась. Чужие URL не трогаем."""
    if not url or not url.startswith(LOCAL_PREFIX):
        return
    name = url[len(LOCAL_PREFIX):]
    if not _NAME_RE.fullmatch(name) or "/" in name:
        return
    try:
        os.remove(os.path.join(UPLOAD_DIR, name))
    except OSError:
        pass
