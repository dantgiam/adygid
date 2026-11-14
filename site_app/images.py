"""Адаптивные фото через трансформацию Supabase Storage.

На живом проекте (проверка 14 ноября 2026) публичный endpoint
``/storage/v1/render/image/public/...?width=&resize=contain&quality=&format=webp``
отдаёт WebP нужной ширины. Без ``resize=contain`` сервер меняет только ширину
и ломает пропорции, поэтому contain обязателен.

Оригиналы в хранилище не трогаем: меняется только URL в разметке. Не-Supabase
ссылки (локальные /assets, иконки) проходят без изменений.
"""
from __future__ import annotations

import re
from html import escape, unescape
from typing import Iterable, Optional

OBJECT_MARK = "/storage/v1/object/public/"
RENDER_MARK = "/storage/v1/render/image/public/"
DEFAULT_WIDTHS = (480, 800, 1280)
DEFAULT_QUALITY = 70
DEFAULT_SRC_WIDTH = 800
CARD_SIZES = "(max-width: 640px) 92vw, (max-width: 1024px) 45vw, 400px"
HERO_SIZES = "(max-width: 1100px) 100vw, 1100px"
ARTICLE_SIZES = "(max-width: 800px) 100vw, 800px"
FAQ_SIZES = "72px"
HOME_PHOTO_SIZES = "(max-width: 640px) 42vw, 400px"
SEASONAL_SIZES = "(max-width: 640px) 92vw, 360px"
PODBOR_STOP_SIZES = "(max-width: 640px) 92vw, 420px"

_IMG_RE = re.compile(r"<img\b([^>]*?)(/?)>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([^\s=]+)(?:\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+)))?', re.IGNORECASE)


def is_transformable(url: Optional[str]) -> bool:
    if not url:
        return False
    return OBJECT_MARK in url or RENDER_MARK in url


def _split_public(url: str) -> Optional[tuple[str, str]]:
    """Вернуть (origin, bucket/key без query) или None, если это не наше хранилище."""
    for mark in (OBJECT_MARK, RENDER_MARK):
        idx = url.find(mark)
        if idx == -1:
            continue
        origin = url[:idx]
        rest = url[idx + len(mark):].split("?", 1)[0].split("#", 1)[0]
        if not rest:
            return None
        return origin, rest
    return None


def transform_url(
    url: Optional[str],
    width: int = DEFAULT_SRC_WIDTH,
    quality: int = DEFAULT_QUALITY,
) -> str:
    """URL ужатого WebP; для чужих адресов — исходная строка."""
    if not url:
        return ""
    parts = _split_public(url)
    if not parts:
        return url
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = DEFAULT_SRC_WIDTH
    if width < 16:
        return url
    origin, rest = parts
    return (
        f"{origin}{RENDER_MARK}{rest}"
        f"?width={width}&resize=contain&quality={int(quality)}&format=webp"
    )


def srcset(
    url: Optional[str],
    widths: Iterable[int] = DEFAULT_WIDTHS,
    quality: int = DEFAULT_QUALITY,
) -> str:
    if not is_transformable(url):
        return ""
    seen: list[int] = []
    for raw in widths:
        try:
            width = int(raw)
        except (TypeError, ValueError):
            continue
        if width < 16 or width in seen:
            continue
        seen.append(width)
    return ", ".join(
        f"{transform_url(url, width, quality)} {width}w" for width in seen
    )


def default_src(
    url: Optional[str],
    width: int = DEFAULT_SRC_WIDTH,
    quality: int = DEFAULT_QUALITY,
) -> str:
    if not url:
        return ""
    if is_transformable(url):
        return transform_url(url, width, quality)
    return url


def _parse_attrs(raw: str) -> list[tuple[str, Optional[str]]]:
    """Сохранить порядок атрибутов и значение (уже без кавычек)."""
    out: list[tuple[str, Optional[str]]] = []
    for match in _ATTR_RE.finditer(raw):
        name = match.group(1)
        if match.group(2) is None:
            out.append((name, None))
            continue
        value = match.group(3)
        if value is None:
            value = match.group(4)
        if value is None:
            value = match.group(5) or ""
        out.append((name, value))
    return out


def _attr_map(pairs: list[tuple[str, Optional[str]]]) -> dict[str, Optional[str]]:
    return {name.lower(): value for name, value in pairs}


def _rebuild(pairs: list[tuple[str, Optional[str]]], updates: dict[str, str], closing: str) -> str:
    used = set()
    parts: list[str] = []
    for name, value in pairs:
        key = name.lower()
        if key in updates:
            parts.append(f'{name}="{escape(updates[key], quote=True)}"')
            used.add(key)
        elif value is None:
            parts.append(name)
        else:
            parts.append(f'{name}="{escape(unescape(value), quote=True)}"')
    for key, value in updates.items():
        if key not in used:
            parts.append(f'{key}="{escape(value, quote=True)}"')
    slash = " /" if closing.strip() == "/" else ""
    return "<img " + " ".join(parts) + slash + ">"


def enhance_html_images(
    html: Optional[str],
    sizes: str = ARTICLE_SIZES,
    src_width: int = DEFAULT_SRC_WIDTH,
) -> str:
    """Добавляет srcset к <img> из хранилища, не меняя alt/подписи и набор кадров."""
    if not html or not is_transformable(html):
        return html or ""

    def repl(match: re.Match[str]) -> str:
        pairs = _parse_attrs(match.group(1))
        attrs = _attr_map(pairs)
        src = unescape(attrs.get("src") or "")
        if not is_transformable(src):
            return match.group(0)
        updates = {
            "src": transform_url(src, src_width),
            "srcset": srcset(src),
        }
        if not attrs.get("sizes"):
            updates["sizes"] = sizes
        if not attrs.get("decoding"):
            updates["decoding"] = "async"
        if not attrs.get("loading") and (attrs.get("fetchpriority") or "").lower() != "high":
            updates["loading"] = "lazy"
        return _rebuild(pairs, updates, match.group(2) or "")

    return _IMG_RE.sub(repl, html)
