import io
import os
import secrets
import uuid
from typing import Optional, List

import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, func, text
from geoalchemy2.shape import to_shape
from shapely.geometry import shape, mapping
from pydantic import BaseModel
from PIL import Image

from app.database import Base, engine, get_db
from app.models import Trail, TrailSegment, Checkpoint, Photo, Category, Article, Like
from app.slugs import slugify as _slugify, unique_slug as _unique_slug
from site_app.router import router as site_router

app = FastAPI(title="АдыГид API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_browser_cache(request, call_next):
    """Проект активно меняется — без этого браузер может показывать старую
    версию страницы/админки после правок, пока не сделаешь жёсткий рефреш."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

Base.metadata.create_all(bind=engine)

# ─────────────────────────────────────────────
#  Лёгкая идемпотентная "миграция" — в проекте нет Alembic, а create_all
#  не умеет добавлять колонки в уже существующие таблицы. Каждый ALTER
#  безопасно повторять при каждом старте (IF NOT EXISTS).
# ─────────────────────────────────────────────
_EXTRA_CRITERIA_DDL = [
    "difficulty VARCHAR(20) NOT NULL DEFAULT 'medium'",
    "surface_types TEXT[] NOT NULL DEFAULT '{}'",
    "seasonality VARCHAR(20) NOT NULL DEFAULT 'year_round'",
    "weather_warning BOOLEAN NOT NULL DEFAULT false",
    "access_type VARCHAR(30) NOT NULL DEFAULT 'foot_only'",
    "is_paid BOOLEAN NOT NULL DEFAULT false",
    "price_note VARCHAR(255)",
    "equipment_tags TEXT[] NOT NULL DEFAULT '{}'",
    "kid_friendly BOOLEAN NOT NULL DEFAULT false",
    "district VARCHAR(30)",
    "popularity VARCHAR(20) NOT NULL DEFAULT 'normal'",
]
with engine.begin() as _conn:
    for _table in ("trails", "checkpoints"):
        for _col_ddl in _EXTRA_CRITERIA_DDL:
            _conn.execute(text(f"ALTER TABLE {_table} ADD COLUMN IF NOT EXISTS {_col_ddl}"))
    _conn.execute(text("ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS duration_minutes INTEGER"))
    _conn.execute(text("ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT true"))
    _conn.execute(text("ALTER TABLE articles ADD COLUMN IF NOT EXISTS faq JSONB NOT NULL DEFAULT '[]'::jsonb"))
    # DEFAULT true — все точки, заведённые до появления флага, уже показывались
    # в «Местах», и сайт после миграции не должен измениться.
    _conn.execute(text("ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS show_as_place BOOLEAN NOT NULL DEFAULT true"))

# Дефолтные категории — засеваются один раз при первом старте, если таблица пустая
_DEFAULT_CATEGORIES = [
    # публичные типы мест (показываются в фильтрах на сайте)
    ("Водопад", "checkpoint", "💧", True),
    ("Смотровая", "checkpoint", "👁", True),
    ("Пещера", "checkpoint", "🕳", True),
    ("Каньон / ущелье", "checkpoint", "🏞", True),
    ("Плато / гора", "checkpoint", "⛰", True),
    ("Дольмен", "checkpoint", "🗿", True),
    ("Термальный источник", "checkpoint", "♨️", True),
    ("Река / озеро", "checkpoint", "💦", True),
    ("Монастырь / храм", "checkpoint", "⛪", True),
    ("Заповедник / парк", "checkpoint", "🌲", True),
    ("Аул / этнообъект", "checkpoint", "🏘", True),
    ("Музей", "checkpoint", "🏛", True),
    ("Скала-памятник", "checkpoint", "🪨", True),
    ("Археологический объект", "checkpoint", "⛏", True),
    # типы маршрутов
    ("Пеший", "trail", "🥾", True),
    ("Конный", "trail", "🐎", True),
    ("Джип-тур", "trail", "🚙", True),
    ("Сплав", "trail", "🛶", True),
    # служебные метки — только для редактора в админке, не показываются гостю
    ("Стоянка / кэмпинг", "checkpoint", "⛺", False),
    ("Начало маршрута", "checkpoint", "🚩", False),
    ("Конец маршрута", "checkpoint", "🏁", False),
    ("Другое", "both", "📍", False),
]
with Session(engine) as _seed_db:
    _existing_names = {row[0] for row in _seed_db.execute(select(Category.name)).all()}
    for name, type_, icon, is_public in _DEFAULT_CATEGORIES:
        if name not in _existing_names:
            _seed_db.add(Category(name=name, type=type_, icon=icon, is_public=is_public))
    # у категорий, заведённых ещё до появления is_public, флаг мог остаться
    # дефолтным (True) — принудительно приводим служебные метки в порядок
    _service_names = [name for name, _, _, is_public in _DEFAULT_CATEGORIES if not is_public]
    for _c in _seed_db.execute(select(Category).where(Category.name.in_(_service_names))).scalars():
        _c.is_public = False
    _seed_db.commit()


# ─────────────────────────────────────────────
#  Авторизация админки (HTTP Basic)
# ─────────────────────────────────────────────

security = HTTPBasic()
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adygid")


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# ─────────────────────────────────────────────
#  Загрузка фото (Supabase Storage)
# ─────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "uploads")

ALLOWED_EXT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
THUMB_SIZE = (480, 480)
_PUBLIC_URL_PREFIX = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/"


def _storage_headers(content_type: str) -> dict:
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
    }


async def _storage_upload(object_path: str, data: bytes, content_type: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{object_path}",
            content=data,
            headers=_storage_headers(content_type),
        )
    if resp.status_code >= 400:
        raise HTTPException(502, f"Не удалось загрузить файл в хранилище: {resp.text}")


def _delete_uploaded_files(photo: "Photo"):
    paths = [
        url.removeprefix(_PUBLIC_URL_PREFIX)
        for url in (photo.url, photo.thumb_url)
        if url and url.startswith(_PUBLIC_URL_PREFIX)
    ]
    if not paths:
        return
    try:
        httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}",
            json={"prefixes": paths},
            headers=_storage_headers("application/json"),
            timeout=10,
        )
    except httpx.HTTPError:
        pass


@app.post("/api/uploads/photo")
async def upload_photo(file: UploadFile = File(...), _: bool = Depends(require_admin)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Разрешены только файлы jpg, png, webp")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Файл слишком большой (максимум 8MB)")

    name = uuid.uuid4().hex
    content_type = CONTENT_TYPES[ext]

    thumb_data = data
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail(THUMB_SIZE)
        if ext in ("jpg", "jpeg") and img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, ALLOWED_EXT[ext])
        thumb_data = buf.getvalue()
    except Exception:
        pass

    orig_object = f"{name}.{ext}"
    thumb_object = f"{name}_thumb.{ext}"
    await _storage_upload(orig_object, data, content_type)
    await _storage_upload(thumb_object, thumb_data, content_type)

    return {
        "url": f"{_PUBLIC_URL_PREFIX}{orig_object}",
        "thumb_url": f"{_PUBLIC_URL_PREFIX}{thumb_object}",
    }


# ─────────────────────────────────────────────
#  Pydantic-схемы (прямо здесь, без отдельного файла)
# ─────────────────────────────────────────────

class ExtraCriteriaIn(BaseModel):
    """Общие для Trail и Checkpoint критерии фильтрации (adygid_filters_spec.md)."""
    difficulty: Optional[str] = None
    surface_types: Optional[List[str]] = None
    seasonality: Optional[str] = None
    weather_warning: Optional[bool] = None
    access_type: Optional[str] = None
    is_paid: Optional[bool] = None
    price_note: Optional[str] = None
    equipment_tags: Optional[List[str]] = None
    kid_friendly: Optional[bool] = None
    district: Optional[str] = None
    popularity: Optional[str] = None

class TrailIn(ExtraCriteriaIn):
    name: str
    description: Optional[str] = None
    category_id: Optional[int] = None
    duration_minutes: Optional[int] = None

class TrailUpdate(ExtraCriteriaIn):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    duration_minutes: Optional[int] = None

class SegmentIn(BaseModel):
    difficulty: str = "easy"      # easy | medium | hard
    order_index: int = 0
    geojson: dict                 # GeoJSON LineString

class SegmentUpdate(BaseModel):
    difficulty: Optional[str] = None
    order_index: Optional[int] = None
    geojson: Optional[dict] = None

class CheckpointIn(ExtraCriteriaIn):
    trail_id: Optional[int] = None
    name: str
    category_id: Optional[int] = None
    description: Optional[str] = None
    order_index: int = 0
    duration_minutes: Optional[int] = None
    show_as_place: Optional[bool] = None
    lon: float
    lat: float

class CheckpointUpdate(ExtraCriteriaIn):
    name: Optional[str] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    order_index: Optional[int] = None
    duration_minutes: Optional[int] = None
    show_as_place: Optional[bool] = None
    lon: Optional[float] = None
    lat: Optional[float] = None

class CheckpointOrderIn(BaseModel):
    """Новый порядок точек маршрута — список id в нужной последовательности."""
    ids: List[int]

class PhotoIn(BaseModel):
    url: str
    thumb_url: Optional[str] = None
    caption: Optional[str] = None

class CategoryIn(BaseModel):
    name: str
    type: str = "both"            # trail | checkpoint | both
    icon: Optional[str] = None
    is_public: bool = True

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    icon: Optional[str] = None
    is_public: Optional[bool] = None


class FAQItemIn(BaseModel):
    question: str
    answer: str

class ArticleIn(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    cover_url: Optional[str] = None
    body: str = ""
    faq: Optional[List[FAQItemIn]] = None
    district: Optional[str] = None
    featured_checkpoint_ids: Optional[List[int]] = None
    featured_trail_ids: Optional[List[int]] = None
    is_published: bool = True

class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    cover_url: Optional[str] = None
    body: Optional[str] = None
    faq: Optional[List[FAQItemIn]] = None
    district: Optional[str] = None
    featured_checkpoint_ids: Optional[List[int]] = None
    featured_trail_ids: Optional[List[int]] = None
    is_published: Optional[bool] = None


_EXTRA_CRITERIA_FIELDS = [
    "difficulty", "surface_types", "seasonality", "weather_warning",
    "access_type", "is_paid", "price_note", "equipment_tags", "kid_friendly",
    "district", "popularity",
]


def _extra_criteria_kwargs(body: ExtraCriteriaIn) -> dict:
    """Только переданные (не-None) критерии фильтрации — чтобы не затирать DB-дефолты None-ами."""
    return {f: getattr(body, f) for f in _EXTRA_CRITERIA_FIELDS if getattr(body, f) is not None}


def _apply_extra_criteria(obj, body: ExtraCriteriaIn):
    for f in _EXTRA_CRITERIA_FIELDS:
        value = getattr(body, f)
        if value is not None:
            setattr(obj, f, value)


# ─────────────────────────────────────────────
#  CATEGORIES
# ─────────────────────────────────────────────

@app.get("/api/categories")
def list_categories(type: Optional[str] = None, db: Session = Depends(get_db)):
    cats = db.execute(select(Category)).scalars().all()
    if type:
        cats = [c for c in cats if c.type == type or c.type == "both"]
    return [_category_out(c) for c in cats]


@app.post("/api/categories", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    c = Category(name=body.name, type=body.type, icon=body.icon, is_public=body.is_public)
    db.add(c); db.commit(); db.refresh(c)
    return _category_out(c)


@app.patch("/api/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    c = _get_or_404(db, Category, cat_id)
    if body.name is not None: c.name = body.name
    if body.type is not None: c.type = body.type
    if body.icon is not None: c.icon = body.icon
    if body.is_public is not None: c.is_public = body.is_public
    db.commit(); db.refresh(c)
    return _category_out(c)


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    c = _get_or_404(db, Category, cat_id)
    db.delete(c); db.commit()
    return {"ok": True}


def _category_out(c: Category):
    return {"id": c.id, "name": c.name, "type": c.type, "icon": c.icon, "is_public": c.is_public}


# ─────────────────────────────────────────────
#  TRAILS
# ─────────────────────────────────────────────

@app.get("/api/trails")
def list_trails(db: Session = Depends(get_db)):
    trails = db.execute(select(Trail)).scalars().all()
    return [_trail_out(t) for t in trails]


@app.post("/api/trails", status_code=201)
def create_trail(body: TrailIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    t = Trail(
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        duration_minutes=body.duration_minutes,
        **_extra_criteria_kwargs(body),
    )
    db.add(t); db.commit(); db.refresh(t)
    return _trail_out(t)


@app.patch("/api/trails/{trail_id}")
def update_trail(trail_id: int, body: TrailUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    t = _get_or_404(db, Trail, trail_id)
    if body.name is not None:              t.name = body.name
    if body.description is not None:       t.description = body.description
    if body.category_id is not None:       t.category_id = body.category_id
    if body.duration_minutes is not None:  t.duration_minutes = body.duration_minutes
    _apply_extra_criteria(t, body)
    db.commit(); db.refresh(t)
    return _trail_out(t)


@app.delete("/api/trails/{trail_id}")
def delete_trail(trail_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    t = _get_or_404(db, Trail, trail_id)
    for p in list(t.photos):
        _delete_uploaded_files(p)
    for cp in t.checkpoints:
        for p in list(cp.photos):
            _delete_uploaded_files(p)
    db.delete(t); db.commit()
    return {"ok": True}


@app.post("/api/trails/{trail_id}/photos", status_code=201)
def add_trail_photo(trail_id: int, body: PhotoIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    _get_or_404(db, Trail, trail_id)
    photo = Photo(trail_id=trail_id, url=body.url, thumb_url=body.thumb_url, caption=body.caption)
    db.add(photo); db.commit(); db.refresh(photo)
    return _photo_out(photo)


def _extra_criteria_out(obj):
    return {
        "difficulty": obj.difficulty,
        "surface_types": obj.surface_types or [],
        "seasonality": obj.seasonality,
        "weather_warning": obj.weather_warning,
        "access_type": obj.access_type,
        "is_paid": obj.is_paid,
        "price_note": obj.price_note,
        "equipment_tags": obj.equipment_tags or [],
        "kid_friendly": obj.kid_friendly,
    }


def _trail_out(t: Trail):
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category_id": t.category_id,
        "category": _category_out(t.category) if t.category else None,
        "duration_minutes": t.duration_minutes,
        "segments": [_seg_out(s) for s in t.segments],
        "checkpoints": [_cp_out(c) for c in t.checkpoints],
        "photos": [_photo_out(p) for p in t.photos],
        **_extra_criteria_out(t),
    }


# ─────────────────────────────────────────────
#  SEGMENTS
# ─────────────────────────────────────────────

@app.get("/api/trails/{trail_id}/segments")
def list_segments(trail_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, Trail, trail_id)
    segs = db.execute(select(TrailSegment).where(TrailSegment.trail_id == trail_id)).scalars().all()
    return [_seg_out(s) for s in segs]


@app.post("/api/trails/{trail_id}/segments", status_code=201)
def add_segment(trail_id: int, body: SegmentIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    _get_or_404(db, Trail, trail_id)
    wkt = shape(body.geojson).wkt
    seg = TrailSegment(
        trail_id=trail_id,
        difficulty=body.difficulty,
        order_index=body.order_index,
        geom=f"SRID=4326;{wkt}",
    )
    db.add(seg); db.commit(); db.refresh(seg)
    return _seg_out(seg)


@app.patch("/api/segments/{seg_id}")
def update_segment(seg_id: int, body: SegmentUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    seg = _get_or_404(db, TrailSegment, seg_id)
    if body.difficulty is not None:  seg.difficulty = body.difficulty
    if body.order_index is not None: seg.order_index = body.order_index
    if body.geojson is not None:
        wkt = shape(body.geojson).wkt
        seg.geom = f"SRID=4326;{wkt}"
    db.commit(); db.refresh(seg)
    return _seg_out(seg)


@app.delete("/api/segments/{seg_id}")
def delete_segment(seg_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    seg = _get_or_404(db, TrailSegment, seg_id)
    db.delete(seg); db.commit()
    return {"ok": True}


def _seg_out(s: TrailSegment):
    shp = to_shape(s.geom)
    return {
        "id": s.id,
        "trail_id": s.trail_id,
        "difficulty": s.difficulty,
        "order_index": s.order_index,
        "geojson": mapping(shp),
    }


# ─────────────────────────────────────────────
#  CHECKPOINTS
# ─────────────────────────────────────────────

@app.get("/api/checkpoints")
def list_all_checkpoints(db: Session = Depends(get_db)):
    cps = db.execute(select(Checkpoint)).scalars().all()
    return [_cp_out(c) for c in cps]


@app.get("/api/checkpoints/nearby")
def nearby_checkpoints(lat: float, lon: float, limit: int = 10, db: Session = Depends(get_db)):
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_DistanceSphere(Checkpoint.geom, point).label("distance_m")
    rows = db.execute(select(Checkpoint, dist).order_by(dist).limit(limit)).all()
    result = []
    for cp, distance_m in rows:
        out = _cp_out(cp)
        out["distance_km"] = round(distance_m / 1000, 2)
        result.append(out)
    return result


@app.get("/api/trails/{trail_id}/checkpoints")
def list_checkpoints(trail_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, Trail, trail_id)
    cps = db.execute(select(Checkpoint).where(Checkpoint.trail_id == trail_id)).scalars().all()
    return [_cp_out(c) for c in cps]


@app.post("/api/checkpoints", status_code=201)
def create_checkpoint(body: CheckpointIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    # Отдельно стоящая точка — это всегда место на сайте; точка внутри маршрута
    # по умолчанию только его часть, пока её явно не «выделили».
    show_as_place = body.show_as_place if body.show_as_place is not None else (body.trail_id is None)
    cp = Checkpoint(
        trail_id=body.trail_id,
        name=body.name,
        category_id=body.category_id,
        description=body.description,
        order_index=body.order_index,
        duration_minutes=body.duration_minutes,
        show_as_place=show_as_place,
        geom=f"SRID=4326;POINT({body.lon} {body.lat})",
        **_extra_criteria_kwargs(body),
    )
    db.add(cp); db.commit(); db.refresh(cp)
    return _cp_out(cp)


@app.patch("/api/checkpoints/{cp_id}")
def update_checkpoint(cp_id: int, body: CheckpointUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    cp = _get_or_404(db, Checkpoint, cp_id)
    if body.name is not None:        cp.name = body.name
    if body.category_id is not None: cp.category_id = body.category_id
    if body.description is not None: cp.description = body.description
    if body.order_index is not None: cp.order_index = body.order_index
    if body.duration_minutes is not None: cp.duration_minutes = body.duration_minutes
    if body.show_as_place is not None: cp.show_as_place = body.show_as_place
    if body.lon is not None and body.lat is not None:
        cp.geom = f"SRID=4326;POINT({body.lon} {body.lat})"
    _apply_extra_criteria(cp, body)
    db.commit(); db.refresh(cp)
    return _cp_out(cp)


@app.patch("/api/trails/{trail_id}/checkpoints/order")
def reorder_checkpoints(trail_id: int, body: CheckpointOrderIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    """Перестановка точек маршрута — принимает полный список id в новом порядке.
    Чужие точки игнорируем, чтобы кривой запрос не растащил другие маршруты."""
    _get_or_404(db, Trail, trail_id)
    own = {
        cp.id: cp
        for cp in db.execute(select(Checkpoint).where(Checkpoint.trail_id == trail_id)).scalars().all()
    }
    for index, cp_id in enumerate(body.ids):
        cp = own.get(cp_id)
        if cp is not None:
            cp.order_index = index
    db.commit()
    return {"ok": True}


@app.delete("/api/checkpoints/{cp_id}")
def delete_checkpoint(cp_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    cp = _get_or_404(db, Checkpoint, cp_id)
    for p in list(cp.photos):
        _delete_uploaded_files(p)
    db.delete(cp); db.commit()
    return {"ok": True}


@app.post("/api/checkpoints/{cp_id}/photos", status_code=201)
def add_photo(cp_id: int, body: PhotoIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    _get_or_404(db, Checkpoint, cp_id)
    photo = Photo(checkpoint_id=cp_id, url=body.url, thumb_url=body.thumb_url, caption=body.caption)
    db.add(photo); db.commit(); db.refresh(photo)
    return _photo_out(photo)


@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    photo = _get_or_404(db, Photo, photo_id)
    _delete_uploaded_files(photo)
    db.delete(photo); db.commit()
    return {"ok": True}


def _photo_out(p: Photo):
    return {"id": p.id, "url": p.url, "thumb_url": p.thumb_url, "caption": p.caption}


def _cp_out(c: Checkpoint):
    shp = to_shape(c.geom)
    return {
        "id": c.id,
        "trail_id": c.trail_id,
        "name": c.name,
        "category_id": c.category_id,
        "category": _category_out(c.category) if c.category else None,
        "description": c.description,
        "order_index": c.order_index,
        "duration_minutes": c.duration_minutes,
        "show_as_place": c.show_as_place,
        "lon": shp.x,
        "lat": shp.y,
        "photos": [_photo_out(p) for p in c.photos],
        **_extra_criteria_out(c),
    }


# ─────────────────────────────────────────────
#  EQUIPMENT TAGS (для автокомплита в админке)
# ─────────────────────────────────────────────

@app.get("/api/equipment-tags")
def list_equipment_tags(db: Session = Depends(get_db)):
    tags = set()
    for row in db.execute(select(Trail.equipment_tags)).scalars():
        if row: tags.update(row)
    for row in db.execute(select(Checkpoint.equipment_tags)).scalars():
        if row: tags.update(row)
    return sorted(tags)


# ─────────────────────────────────────────────
#  ARTICLES
# ─────────────────────────────────────────────

@app.get("/api/articles")
def list_articles(db: Session = Depends(get_db)):
    arts = db.execute(select(Article).order_by(Article.created_at.desc())).scalars().all()
    return [_article_out(a) for a in arts]


@app.get("/api/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    a = _get_or_404(db, Article, article_id)
    return _article_out(a)


@app.post("/api/articles", status_code=201)
def create_article(body: ArticleIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    slug = _unique_slug(db, _slugify(body.slug or body.title))
    a = Article(
        title=body.title,
        slug=slug,
        excerpt=body.excerpt,
        cover_url=body.cover_url,
        body=body.body,
        faq=[item.model_dump() for item in body.faq] if body.faq is not None else [],
        district=body.district,
        featured_checkpoint_ids=body.featured_checkpoint_ids or [],
        featured_trail_ids=body.featured_trail_ids or [],
        is_published=body.is_published,
    )
    db.add(a); db.commit(); db.refresh(a)
    return _article_out(a)


@app.patch("/api/articles/{article_id}")
def update_article(article_id: int, body: ArticleUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    a = _get_or_404(db, Article, article_id)
    if body.title is not None: a.title = body.title
    if body.slug is not None: a.slug = _unique_slug(db, _slugify(body.slug), exclude_id=article_id)
    if body.excerpt is not None: a.excerpt = body.excerpt
    if body.cover_url is not None: a.cover_url = body.cover_url
    if body.body is not None: a.body = body.body
    if body.faq is not None: a.faq = [item.model_dump() for item in body.faq]
    if body.district is not None: a.district = body.district
    if body.featured_checkpoint_ids is not None: a.featured_checkpoint_ids = body.featured_checkpoint_ids
    if body.featured_trail_ids is not None: a.featured_trail_ids = body.featured_trail_ids
    if body.is_published is not None: a.is_published = body.is_published
    db.commit(); db.refresh(a)
    return _article_out(a)


@app.delete("/api/articles/{article_id}")
def delete_article(article_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    a = _get_or_404(db, Article, article_id)
    db.delete(a); db.commit()
    return {"ok": True}


def _article_out(a: Article):
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "excerpt": a.excerpt,
        "cover_url": a.cover_url,
        "body": a.body,
        "faq": a.faq or [],
        "district": a.district,
        "featured_checkpoint_ids": a.featured_checkpoint_ids or [],
        "featured_trail_ids": a.featured_trail_ids or [],
        "is_published": a.is_published,
    }


# ─────────────────────────────────────────────
#  PREVIEW — прогоняем несохранённый текст через тот же рендер, что и сайт,
#  чтобы предпросмотр в админке не разъезжался с реальной страницей.
# ─────────────────────────────────────────────

class PreviewIn(BaseModel):
    kind: str = "article"          # article | description
    html: str = ""


@app.post("/api/preview")
def render_preview(body: PreviewIn, _: bool = Depends(require_admin)):
    from site_app.router import _add_toc_anchors, _render_article_gallery, _rich_text_html

    rendered = _rich_text_html(body.html)
    if body.kind == "article":
        rendered = _render_article_gallery(rendered)
        rendered, _toc = _add_toc_anchors(rendered)
    return {"html": rendered}


# ─────────────────────────────────────────────
#  STATIC
# ─────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="site_app/static"), name="site_static")
app.include_router(site_router)

@app.get("/map")
def public_map():
    return FileResponse("static/map.html")

@app.get("/m")
def mobile_preview():
    """Превью сайта в рамке телефона (Samsung Galaxy S24 Ultra, 480×1069 CSS px,
    DPR 3.5 — как в чипе устройств Chrome DevTools) — чтобы смотреть мобильную
    вёрстку без реального телефона под рукой."""
    return FileResponse("static/mobile-preview.html")

@app.get("/admin")
def admin(_: bool = Depends(require_admin)):
    return FileResponse("static/admin.html")


# ─────────────────────────────────────────────
#  helpers
# ─────────────────────────────────────────────

def _get_or_404(db, model, id_):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj
