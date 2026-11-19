"""Адреса страниц мест и маршрутов: /mesta/<slug>, /marshruty/<slug>.

Слаг — канонический адрес. Числовой /mesta/<id> навсегда отвечает 301 на
слаг (ссылки из ботов, QR-табличек, чужих постов и старой выдачи), поэтому
в базе тексты статей и сценариев по-прежнему ссылаются на /mesta/<id>:
такая ссылка не ломается при смене слага, а при выводе страницы
rewrite_links() подменяет её на текущий слаг — внутренние ссылки сайта
ведут сразу на канонический адрес, без лишнего редиректа.
"""
import re
import threading
import time
from typing import Optional

from markupsafe import Markup
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Checkpoint, Trail

PREFIX = {"place": "/mesta", "route": "/marshruty"}
_MODEL = {"place": Checkpoint, "route": Trail}
_SEGMENT = {"mesta": "place", "marshruty": "route"}


def place_url(cp) -> str:
    return f"/mesta/{getattr(cp, 'slug', None) or cp.id}"


def route_url(t) -> str:
    return f"/marshruty/{getattr(t, 'slug', None) or t.id}"


class _SlugIndex:
    """id → слаг для подмены ссылок в готовом HTML. Живёт в памяти процесса:
    обновляется после любой правки через админку (invalidate) и раз в минуту
    сам — на случай нескольких воркеров. Неизвестный id перечитывает таблицу
    не чаще раза в секунду (свежесозданная карточка)."""

    TTL = 60.0

    def __init__(self):
        self._lock = threading.Lock()
        self._map: dict[str, dict[int, str]] = {"place": {}, "route": {}}
        self._at = 0.0

    def invalidate(self) -> None:
        self._at = 0.0

    def _load(self) -> None:
        db = SessionLocal()
        try:
            fresh = {}
            # Только страницы, которые открываются: ссылка на скрытую карточку
            # или промежуточную точку маршрута остаётся как была (и как
            # раньше отвечает 404), а её слаг не светится в разметке.
            for kind, model in _MODEL.items():
                q = select(model.id, model.slug).where(model.slug.isnot(None), model.is_published == True)
                if model is Checkpoint:
                    q = q.where(Checkpoint.show_as_place == True)
                fresh[kind] = {i: s for i, s in db.execute(q).all()}
        finally:
            db.close()
        self._map = fresh
        self._at = time.monotonic()

    def fresh(self) -> dict:
        if time.monotonic() - self._at > self.TTL:
            with self._lock:
                if time.monotonic() - self._at > self.TTL:
                    self._load()
        return self._map

    def slug(self, kind: str, obj_id: int) -> Optional[str]:
        self.fresh()
        value = self._map.get(kind, {}).get(obj_id)
        if value is None and time.monotonic() - self._at > 1.0:
            with self._lock:
                if time.monotonic() - self._at > 1.0:
                    self._load()
            value = self._map.get(kind, {}).get(obj_id)
        return value


SLUGS = _SlugIndex()


def invalidate() -> None:
    SLUGS.invalidate()


def id_for_slug(kind: str, slug: str) -> Optional[int]:
    """Обратный поиск для ссылок, вписанных в текст уже слагом."""
    for i, s in SLUGS.fresh().get(kind, {}).items():
        if s == slug:
            return i
    return None


def url_for_id(kind: str, obj_id: int) -> str:
    slug = SLUGS.slug(kind, int(obj_id))
    return f"{PREFIX[kind]}/{slug or obj_id}"


# /mesta/24, /mesta/24#faq, /mesta/24?x=1, https://www.adygid.ru/mesta/24,
# /marshruty/7/track.gpx. Слева — начало строки, кавычка, пробел, скобка или
# наш домен (чужие сайты с /mesta/ в адресе не трогаем); справа — не буква,
# цифра или дефис, чтобы /mesta/24abc остался как есть.
_OWN_HOSTS = r"(?:https?://(?:www\.)?adygid\.ru|https?://localhost(?::\d+)?|https?://127\.0\.0\.1(?::\d+)?)"
_LINK_RE = re.compile(
    r"(?:(?<=[\"'\s(>=:])|^)(" + _OWN_HOSTS + r")?/(mesta|marshruty)/(\d{1,9})(?![\w-])"
)


def rewrite_links(value: str) -> str:
    """Подменить числовые адреса мест и маршрутов на слаги. Ссылки на
    скрытые/удалённые карточки остаются как были (отдадут 404 как и раньше)."""
    if "/mesta/" not in value and "/marshruty/" not in value:
        return value

    def sub(m):
        kind = _SEGMENT[m.group(2)]
        slug = SLUGS.slug(kind, int(m.group(3)))
        return f"{m.group(1) or ''}{PREFIX[kind]}/{slug}" if slug else m.group(0)

    out = _LINK_RE.sub(sub, value)
    return Markup(out) if isinstance(value, Markup) else out


def jinja_finalize(value):
    """Финализатор Jinja: каждый {{ ... }} шаблонов сайта проходит через
    подмену ссылок — так покрываются и тексты из базы (статьи, сценарии,
    округа, FAQ), и JSON для скриптов, и любые url-поля карточек."""
    if isinstance(value, str):
        return rewrite_links(value)
    return value
