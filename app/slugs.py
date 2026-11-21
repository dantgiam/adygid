"""Транслитерация и слаги страниц: статьи, места (/mesta/<slug>) и маршруты
(/marshruty/<slug>).

Отдельный модуль (а не app.main), чтобы его можно было импортировать из
скриптов вроде seed_demo.py без побочных эффектов (создание FastAPI-приложения,
повторные ALTER TABLE) — импорт app.main внутри уже открытой транзакции к тем
же таблицам приводит к самоблокировке в Postgres.

Правила слага места и маршрута:
* транслит названия как в адресах Яндекса и уже опубликованных статей
  (х → h, ц → ts, щ → sch, й → y), нижний регистр, дефисы;
* из «Кедровый бор»: термальный бассейн в Цветочном берём часть до двоеточия,
  если в ней хотя бы два слова или имя в кавычках; скобки и кавычки выкидываем;
* не длиннее ~50 символов, обрезка по границе слова;
* только из цифр не бывает: /mesta/24 — это id, поэтому «24» → «mesto-24»;
* при совпадении — суффикс -2, -3…; занятыми считаются и прежние слаги
  других записей (slug_redirects), чтобы старая ссылка не увела на чужую
  страницу;
* при переименовании слаг не меняется сам — адрес стабилен.
"""
import re
import uuid
from typing import Optional

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, object_session

from app.models import Article, AuthorTrip, Checkpoint, SlugRedirect, Trail

_TRANSLIT = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i",
    "й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t",
    "у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"",
    "э":"e","ю":"yu","я":"ya",
}

# Разделы, где у страниц есть числовой id и слаг: kind → (модель, префикс URL,
# слово для слага из одних цифр).
KINDS = {
    "place": (Checkpoint, "/mesta", "mesto"),
    "route": (Trail, "/marshruty", "marshrut"),
    "article": (Article, "/stati", "statya"),
    "trip": (AuthorTrip, "/poezdki", "poezdka"),
}
_MODEL_KIND = {Checkpoint: "place", Trail: "route", Article: "article", AuthorTrip: "trip"}

SLUG_MAX = 50
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Хвостовые предлоги после обрезки: «...-okno-v» → «...-okno».
_TAIL_STOP = {"i", "v", "u", "s", "k", "na", "po", "ot", "do", "za", "iz", "pod", "nad", "pri", "dlya", "ili"}


def slugify(text_: str) -> str:
    out = []
    for ch in (text_ or "").lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug or uuid.uuid4().hex[:8]


def is_valid_slug(value: str) -> bool:
    return bool(value) and len(value) <= 120 and bool(_SLUG_RE.match(value)) and not value.isdigit()


def _trim(slug: str, limit: int = SLUG_MAX) -> str:
    """Обрезка по словам; «слово» — то, что было между пробелами, поэтому
    «лаго-наки» не разрывается на «lago»."""
    words = [w for w in slug.split(" ") if w]
    out: list[str] = []
    for w in words:
        if out and len("-".join(out + [w])) > limit:
            break
        out.append(w)
    while len(out) > 1 and out[-1] in _TAIL_STOP:
        out.pop()
    return "-".join(out)[:limit].strip("-")


def not_digits(slug: str, kind: str) -> str:
    """Слаг из одних цифр перепутался бы с id — добавляем слово раздела."""
    word = KINDS[kind][2] if kind in KINDS else "page"
    if not slug or slug.replace("-", "").isdigit():
        return f"{word}-{slug}".strip("-") if slug else word
    return slug


def entity_slug_base(name: str, kind: str) -> str:
    """Читаемый слаг из названия места или маршрута (без проверки на уникальность)."""
    s = (name or "").strip()
    s = re.sub(r"\([^)]*\)", " ", s)          # «(Кошачий глаз)»
    head, sep, _tail = s.partition(":")
    # «АкваТермо»: термальные бассейны… → akvatermo: имя в кавычках до
    # двоеточия — само по себе название; иначе нужно хотя бы два слова.
    if sep and (len(re.findall(r"\w+", head)) >= 2 or re.fullmatch(r"\s*«[^»]+»\s*", head)):
        s = head
    s = re.sub(r"[«»\"“”„'’]", "", s)
    words = [slugify(w) for w in re.split(r"[\s—–]+", s) if re.search(r"\w", w)]
    return not_digits(_trim(" ".join(w for w in words if w)), kind)


def _taken(conn_or_db, model, slug: str, exclude_id: Optional[int]) -> bool:
    kind = _MODEL_KIND.get(model)
    q = select(model.id).where(model.slug == slug)
    if exclude_id is not None:
        q = q.where(model.id != exclude_id)
    if conn_or_db.execute(q).first() is not None:
        return True
    if kind:
        q = select(SlugRedirect.entity_id).where(SlugRedirect.kind == kind, SlugRedirect.old_slug == slug)
        if exclude_id is not None:
            q = q.where(SlugRedirect.entity_id != exclude_id)
        if conn_or_db.execute(q).first() is not None:
            return True
    return False


def unique_slug(db, base_slug: str, exclude_id: Optional[int] = None, model=Article, reserved=()) -> str:
    """db — Session или Connection. reserved — слаги, уже выданные в этом же flush."""
    kind = _MODEL_KIND.get(model)
    if kind:
        base_slug = not_digits(base_slug, kind)
    slug = base_slug
    i = 2
    while slug in reserved or _taken(db, model, slug, exclude_id):
        slug = f"{base_slug}-{i}"
        i += 1
    return slug


def remember_old_slug(db: Session, kind: str, entity_id: int, old_slug: Optional[str]) -> None:
    """Старый слаг продолжает работать: /<раздел>/<old> → 301 на текущий."""
    if not old_slug:
        return
    row = db.execute(
        select(SlugRedirect).where(SlugRedirect.kind == kind, SlugRedirect.old_slug == old_slug)
    ).scalars().first()
    if row:
        row.entity_id = entity_id
    else:
        db.add(SlugRedirect(kind=kind, old_slug=old_slug, entity_id=entity_id))


def set_slug(db: Session, obj, requested: str) -> str:
    """Смена слага из админки: нормализует, проверяет уникальность и
    оставляет старый адрес редиректом. Возвращает итоговый слаг."""
    model = type(obj)
    kind = _MODEL_KIND[model]
    new = not_digits(slugify(requested)[:120].strip("-"), kind)
    if new == obj.slug:
        return new
    new = unique_slug(db, new, exclude_id=obj.id, model=model)
    old = obj.slug
    obj.slug = new
    remember_old_slug(db, kind, obj.id, old)
    # Если вернули прежний слаг — убираем его из истории, иначе он
    # редиректил бы сам на себя.
    db.execute(
        SlugRedirect.__table__.delete().where(
            SlugRedirect.kind == kind, SlugRedirect.old_slug == new, SlugRedirect.entity_id == obj.id
        )
    )
    return new


# ── Новые места и маршруты получают слаг сами, каким бы путём ни создавались
# (админка, сиды, скрипты импорта, тесты).
def _auto_slug(mapper, connection, target):
    if getattr(target, "slug", None):
        return
    model = type(target)
    kind = _MODEL_KIND[model]
    sess = object_session(target)
    reserved = sess.info.setdefault("_slugs_in_flush", set()) if sess is not None else set()
    slug = unique_slug(connection, entity_slug_base(target.name, kind), model=model, reserved=reserved)
    reserved.add(slug)
    target.slug = slug


for _m in (Checkpoint, Trail):
    event.listen(_m, "before_insert", _auto_slug)


def _auto_trip_slug(mapper, connection, target):
    """Поездка называется title, не name — слаг из заголовка."""
    if getattr(target, "slug", None):
        return
    sess = object_session(target)
    reserved = sess.info.setdefault("_slugs_in_flush", set()) if sess is not None else set()
    slug = unique_slug(connection, entity_slug_base(target.title, "trip"), model=AuthorTrip, reserved=reserved)
    reserved.add(slug)
    target.slug = slug


event.listen(AuthorTrip, "before_insert", _auto_trip_slug)


@event.listens_for(Session, "after_flush_postexec")
def _clear_flush_slugs(session, _ctx):
    session.info.pop("_slugs_in_flush", None)


def backfill_slugs(db: Session) -> int:
    """Проставить слаги записям, у которых их ещё нет (первый запуск после
    миграции). Порядок по id — у старых карточек приоритет на «чистый» слаг."""
    n = 0
    for model, kind in ((Checkpoint, "place"), (Trail, "route")):
        rows = db.execute(select(model).where(model.slug.is_(None)).order_by(model.id)).scalars().all()
        reserved: set[str] = set()
        for obj in rows:
            slug = unique_slug(db, entity_slug_base(obj.name, kind), exclude_id=obj.id, model=model, reserved=reserved)
            reserved.add(slug)
            # Без onupdate: проставление слага — не правка карточки, дата
            # «обновлено» в sitemap не должна сдвигаться.
            db.execute(
                model.__table__.update().where(model.id == obj.id)
                .values(slug=slug, updated_at=model.__table__.c.updated_at)
            )
            n += 1
    return n


MIGRATION_DDL = [
    "ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS slug VARCHAR(120)",
    "ALTER TABLE trails ADD COLUMN IF NOT EXISTS slug VARCHAR(120)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_checkpoints_slug ON checkpoints (slug)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_trails_slug ON trails (slug)",
]


def migrate(engine) -> int:
    """Идемпотентно: колонки, индексы, слаги для записей без слага."""
    with engine.begin() as conn:
        for ddl in MIGRATION_DDL:
            conn.execute(text(ddl))
    with Session(engine) as db:
        n = backfill_slugs(db)
        db.commit()
    return n
