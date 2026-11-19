"""Тексты страниц, которые можно поправить в админке без программиста.

В шаблоне текст пишется так:
    {{ t('home.hero.cta', 'Куда вы едете?') }}     — обычный текст (с **жирным** и [ссылками](/mesta))
    {{ tp('home.meta.title', 'АдыГид — …') }}       — только текст: для <title>, meta, alt
Второй аргумент — текст по умолчанию. Пока в админке ничего не правили,
на сайт выводится ровно он (как раньше). Правка из админки лежит в таблице
site_texts; «Вернуть исходный» удаляет её.

Безопасность: правленый текст всегда экранируется. Из разметки разрешены
только **жирный**, *курсив*, [ссылка](адрес) — адрес http(s)://, /путь, #якорь,
mailto: или tel: — и перенос строки. Произвольный HTML не проходит.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from markupsafe import Markup, escape
from sqlalchemy import text

log = logging.getLogger("adygid.site_texts")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
MAX_LEN = 4000

# Разделы админки: префикс ключа → (название, адрес на сайте).
PAGES = {
    "site": ("Весь сайт: заголовок по умолчанию", "/"),
    "home": ("Главная", "/"),
    "podbor": ("Подбор поездки", "/podbor"),
    "partners": ("Партнёрам", "/partners"),
    "v": ("Впечатления (скрытый тест)", "/v"),
    "nav": ("Меню сайта", "/"),
    "footer": ("Подвал сайта", "/"),
    "places": ("Список мест", "/mesta"),
    "routes": ("Список маршрутов", "/marshruty"),
    "articles": ("Список статей", "/stati"),
    "scenarios": ("Куда поехать", "/kuda"),
    "districts": ("Районы", "/okrugi"),
    "faq": ("Частые вопросы", "/voprosy"),
    "place": ("Карточка места", "/mesta"),
    "notfound": ("Страница 404", "/404-primer"),
}

_CACHE: dict = {"values": None, "at": 0.0}
_CACHE_TTL_S = 30
_LOCK = threading.Lock()


# ───────────────── реестр ключей из шаблонов ─────────────────

_CALL_RE = re.compile(r"""\bt(p?)\(\s*'([a-z0-9_.-]+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)""")


def _unescape_literal(s: str) -> str:
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def scan_templates() -> dict:
    """{ключ: {default, plain, template, page, page_label, url}} по всем шаблонам сайта."""
    out: dict = {}
    for path in sorted(TEMPLATES_DIR.glob("*.html")):
        src = path.read_text(encoding="utf-8")
        for m in _CALL_RE.finditer(src):
            plain, key, default = m.group(1) == "p", m.group(2), _unescape_literal(m.group(3))
            if key in out:
                continue
            page = key.split(".", 1)[0]
            label, url = PAGES.get(page, (page, "/"))
            out[key] = {"key": key, "default": default, "plain": plain, "template": path.name,
                        "page": page, "page_label": label, "url": url,
                        "line": src.count("\n", 0, m.start()) + 1}
    return out


_REGISTRY: dict = {}


def registry() -> dict:
    if not _REGISTRY:
        _REGISTRY.update(scan_templates())
    return _REGISTRY


# ───────────────── правки из базы ─────────────────

def _load() -> dict:
    from app.database import engine
    try:
        with engine.connect() as conn:
            return dict(conn.execute(text("SELECT key, value FROM site_texts")).all())
    except Exception:
        log.exception("site_texts unavailable — тексты по умолчанию")
        return {}


def overrides() -> dict:
    now = time.monotonic()
    with _LOCK:
        if _CACHE["values"] is not None and now - _CACHE["at"] < _CACHE_TTL_S:
            return _CACHE["values"]
    values = _load()
    with _LOCK:
        _CACHE["values"], _CACHE["at"] = values, time.monotonic()
    return values


def invalidate() -> None:
    with _LOCK:
        _CACHE["values"] = None


# ───────────────── безопасная разметка ─────────────────

_SAFE_URL = re.compile(r"^(https?://[^\s<>\"']+|/[^\s<>\"']*|#[\w-]*|mailto:[^\s<>\"']+|tel:[+\d\s()-]+)$")
_LINK_RE = re.compile(r"\[([^\[\]\n]+)\]\(([^()\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![*\w])")


def render_inline(value: str) -> Markup:
    """Экранирует текст и разрешает только **жирный**, *курсив*, [ссылки](…) и переносы."""
    value = (value or "").replace("\x00", "").replace("&nbsp;", "\u00a0").replace("\r\n", "\n")
    links: list = []

    def _link(m):
        label, url = m.group(1), m.group(2).strip()
        if not _SAFE_URL.match(url):
            return m.group(0)
        ext = url.startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener"' if ext else ""
        links.append(Markup('<a href="{}"{}>{}</a>').format(url, Markup(attrs), Markup(_fmt(escape(label)))))
        return f"\x00{len(links) - 1}\x00"

    def _fmt(s) -> str:
        s = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", str(s))
        return _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", s)

    raw = _LINK_RE.sub(_link, value)
    out = _fmt(escape(raw)).replace("\n", "<br>")
    out = re.sub("\x00(\\d+)\x00", lambda m: str(links[int(m.group(1))]), out)
    return Markup(out)


def render_plain(value: str) -> str:
    """Для <title>, meta и alt: без разметки, одной строкой."""
    value = (value or "").replace("&nbsp;", "\u00a0")
    value = _LINK_RE.sub(lambda m: m.group(1), value)
    value = value.replace("**", "")
    return " ".join(value.split())


# ───────────────── функции для шаблонов ─────────────────

def t(key: str, default: str = "") -> Markup:
    v = overrides().get(key)
    if v is None:
        # Текст по умолчанию написан в самом шаблоне — выводим как есть.
        return Markup(default)
    return render_inline(v)


def tp(key: str, default: str = "") -> str:
    v = overrides().get(key)
    if v is None:
        return Markup(default)
    return render_plain(v)


def install(env) -> None:
    env.globals["t"] = t
    env.globals["tp"] = tp


def validate(value: str) -> str:
    value = (value or "").replace("\r\n", "\n").strip()
    if len(value) > MAX_LEN:
        raise ValueError(f"Слишком длинный текст: {len(value)} знаков, можно до {MAX_LEN}")
    return value
