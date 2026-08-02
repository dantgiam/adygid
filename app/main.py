import io
import os
import secrets
import uuid
from html import escape as _esc_html
from typing import Optional, List

import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, func, text
from geoalchemy2.shape import to_shape
from shapely.geometry import shape, mapping
from pydantic import BaseModel
from PIL import Image

from app.database import Base, engine, get_db
from app.models import Trail, TrailSegment, Checkpoint, Photo, Category, Article, Like, Scenario, Magnet, FaqSet
from app.slugs import slugify as _slugify, unique_slug as _unique_slug
from site_app.content import consider_embed_html
from site_app.router import router as site_router

app = FastAPI(title="АдыГид API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _cache_policy(request, call_next):
    """HTML не кэшируем — проект активно меняется, и правки должны быть видны
    сразу. А вот статика (стикеры почти на мегабайт, стили, скрипты, фото)
    раньше тоже отдавалась с no-store, и браузер перекачивал её при каждом
    переходе между страницами — именно это делало навигацию медленной."""
    response = await call_next(request)
    path = request.url.path
    # Стили и скрипты сайта подключаются с ?v=<версия>, фото загружаются под
    # уникальными именами — их можно смело кэшировать надолго. Файлы админки
    # сюда не попадают: она правится часто, а открывает её один человек.
    if path.startswith("/assets/") or path.startswith("/static/uploads/"):
        response.headers["Cache-Control"] = "public, max-age=604800"
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


# Текст страниц сжимается — HTML со списками карточек ужимается в несколько раз
app.add_middleware(GZipMiddleware, minimum_size=800)

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
    _conn.execute(text("ALTER TABLE articles ADD COLUMN IF NOT EXISTS cover_thumb_url VARCHAR(500)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS cover_url VARCHAR(500)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS cover_thumb_url VARCHAR(500)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS tile_cover_url VARCHAR(500)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS tile_cover_thumb_url VARCHAR(500)"))
    # DEFAULT true — все точки, заведённые до появления флага, уже показывались
    # в «Местах», и сайт после миграции не должен измениться.
    _conn.execute(text("ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS show_as_place BOOLEAN NOT NULL DEFAULT true"))
    for _t in ("trails", "checkpoints"):
        _conn.execute(text(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now()"))
        # У записей, заведённых до появления колонки, берём дату создания —
        # иначе на сайте они все окажутся «обновлёнными» в день миграции.
        _conn.execute(text(f"UPDATE {_t} SET updated_at = created_at WHERE updated_at IS NULL"))

# scenarios.tips (отдельный список коротких советов) заменён на локальный
# блок «Что учесть», вставляемый прямо в текст lead — см. site_app.content.
# consider_embed_html. У существующих сценариев с непустыми tips переносим
# советы в конец lead тем же блоком, что теперь строит редактор, и убираем
# колонку — держать данные в двух местах незачем.
with engine.begin() as _conn:
    _has_tips_col = _conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'scenarios' AND column_name = 'tips'"
    )).first()
if _has_tips_col:
    with Session(engine) as _mig_db:
        for _sc in _mig_db.execute(select(Scenario)).scalars().all():
            _tips = _mig_db.execute(text("SELECT tips FROM scenarios WHERE id = :id"), {"id": _sc.id}).scalar() or []
            if not _tips:
                continue
            _lead_html = _sc.lead or ""
            if _lead_html and "<" not in _lead_html:
                _lead_html = "".join(f"<p>{_esc_html(_p.strip())}</p>" for _p in _lead_html.split("\n\n") if _p.strip())
            _sc.lead = _lead_html + consider_embed_html(_tips)
        _mig_db.commit()
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE scenarios DROP COLUMN tips"))

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

# Сценарии — засеваются один раз, если таблица пустая (первый деплой после
# появления фичи). Дальше редактируются только через админку, этот список
# больше не источник истины — не трогаем существующие строки при повторных
# стартах, даже если текст здесь поменяется.
def _seed_lead(text: str, tips: list) -> str:
    """lead хранится как HTML из Quill-редактора — оборачиваем затравочный
    текст и советы «Что учесть» в тот же формат, что строит сам редактор."""
    return f"<p>{_esc_html(text)}</p>" + consider_embed_html(tips)


_DEFAULT_SCENARIOS = [
    dict(
        slug="vpervye", icon="🧭", door="Впервые в Адыгее",
        hint="Что смотреть, если приехали в первый раз",
        title="Впервые в Адыгее: с чего начать",
        lead=_seed_lead(
            "Если вы здесь впервые, начинать стоит не с самого сложного, а с самого показательного. Эти места дают понять, за чем вообще едут в Адыгею, и не требуют ни подготовки, ни специального снаряжения.",
            [
                "Почти всё интересное лежит вдоль одной дороги: Каменномостский — Даховская — Азишский перевал. Отдельно возвращаться никуда не придётся",
                "Двух дней хватает, чтобы увидеть главное без спешки; за один день придётся выбирать между лёгкой прогулкой и выездом на плато",
                "Наличные пригодятся: вход на тропы и парковки не везде принимают карты",
            ],
        ),
        seo_description="Что посмотреть в Адыгее в первый приезд: главные места, сколько закладывать времени и в каком порядке ехать.",
        filter_popularity=["top", "popular"], order_index=0,
    ),
    dict(
        slug="s-detmi", icon="👶", door="Еду с детьми",
        hint="Куда реально дойти с ребёнком",
        title="Адыгея с детьми: куда идти, а что отложить",
        lead=_seed_lead(
            "С детьми в Адыгее нормально — но не везде. Здесь собрано то, что проходится без риска и истерик: короткие оборудованные тропы, тёплая вода и места, где рядом есть кафе и туалет.",
            [
                "Закладывайте вдвое больше времени на любой маршрут — с ребёнком темп другой",
                "Всегда держите план Б рядом: кафе или беседку, если ребёнок устанет раньше, чем закончится тропа",
                "Коляска проедет по основным дорожкам Хаджохской теснины; на тропе к водопадам её лучше не брать — местами придётся нести ребёнка на руках",
            ],
        ),
        seo_description="Адыгея с детьми: какие места и маршруты подходят малышам, где пройдёт коляска и что лучше отложить до школьного возраста.",
        filter_kid_friendly=True, order_index=1,
    ),
    dict(
        slug="bez-mashiny", icon="🚌", door="Без машины",
        hint="Куда попасть на автобусе и пешком",
        title="Адыгея без машины",
        lead=_seed_lead(
            "Без своей машины Адыгея не закрыта — просто круг мест сужается. Сюда попало то, к чему асфальт идёт до самого входа: от Майкопа ходят рейсовые автобусы и маршрутки, дальше пешком или на местном такси.",
            [
                "Базой удобно делать Каменномостский: теснина прямо в посёлке, до тропы к водопадам — пара километров пешком",
                "На плато Лагонаки рейсовый транспорт не идёт — туда только трансфер или экскурсия",
                "Расписание автобусов в сезон плотнее; последний рейс обратно уточняйте заранее",
            ],
        ),
        seo_description="Что посмотреть в Адыгее без машины: места, до которых можно добраться на автобусе, и как построить маршрут.",
        filter_access=["paved"], order_index=2,
    ),
    dict(
        slug="zimoy", icon="❄️", door="Зимой и в межсезонье",
        hint="Что работает, когда наверху снег",
        title="Адыгея зимой и в межсезонье",
        lead=_seed_lead(
            "Зимой высокогорные маршруты закрыты снегом, но поездка не отменяется — меняется набор мест. Здесь то, что работает круглый год: ущелья, пещеры и термальные источники, которые зимой даже выигрывают.",
            [
                "Термальные источники зимой смотрятся эффектнее, чем летом — пар над водой на фоне гор",
                "В пещерах круглый год около +6 °C: зимой это уже не контраст, но тёплая одежда всё равно нужна",
                "Дорогу на плато в снегопад могут закрыть без предупреждения — проверяйте перед выездом",
            ],
        ),
        seo_description="Куда поехать в Адыгее зимой: какие места работают круглый год, что закрыто снегом и чем заняться в межсезонье.",
        filter_seasonality="year_round", order_index=3,
    ),
    dict(
        slug="trekking", icon="🥾", door="Хочу серьёзный треккинг",
        hint="Долгие маршруты и высота",
        title="Серьёзные маршруты Адыгеи",
        lead=_seed_lead(
            "Если прогулочные тропы уже неинтересны — вот то, ради чего сюда едут с рюкзаком: длинные выходы, набор высоты и заповедник. Здесь нужна форма, снаряжение и запас времени на погоду.",
            [
                "В заповедник нужен пропуск, оформлять заранее — на месте это не решается",
                "Погода наверху меняется за полчаса: ветрозащита и тёплая куртка обязательны даже в июле",
                "Оставляйте день в запасе: в горах планы регулярно сдвигаются из-за дождя и тумана",
            ],
        ),
        seo_description="Сложные пешие маршруты Адыгеи: плато Лагонаки, заповедник, многодневные переходы и что для них нужно.",
        filter_difficulty=["hard", "extreme"], order_index=4,
    ),
]
_SCENARIO_ARTICLE_SLUGS = {
    "vpervye": ["chto-posmotret-v-pervuyu-ochered", "edem-v-adygeyu-na-2-3-dnya"],
    "s-detmi": ["adygeya-s-detmi"],
    "bez-mashiny": ["kak-dobratsya-i-gde-ostanovitsya"],
    "zimoy": ["termalnye-istochniki-adygei"],
    "trekking": ["edem-v-adygeyu-na-nedelyu"],
}
with Session(engine) as _seed_db:
    if _seed_db.execute(select(func.count()).select_from(Scenario)).scalar() == 0:
        _slug_to_article_id = dict(_seed_db.execute(select(Article.slug, Article.id)).all())
        for _sc in _DEFAULT_SCENARIOS:
            _sc = dict(_sc)
            _article_ids = [
                _slug_to_article_id[s]
                for s in _SCENARIO_ARTICLE_SLUGS.get(_sc["slug"], [])
                if s in _slug_to_article_id
            ]
            _seed_db.add(Scenario(featured_article_ids=_article_ids, **_sc))
        _seed_db.commit()

# Четыре лид-магнита под самые частые запросы. Ссылки намеренно пустые —
# их проставляет автор в админке, а до тех пор блок на сайте не выводится,
# чтобы не публиковать кнопку, ведущую в никуда.
_DEFAULT_MAGNETS = [
    dict(
        name="Чек-лист снаряжения",
        title="Забыть что-то в горах обиднее, чем не взять лишнее",
        text="Я собрал чек-лист по сезонам: что реально нужно летом, что зимой и что не пригодится никогда. Лежит в закреплённых сообщениях клуба, забирать бесплатно.",
        button_text="Забрать чек-лист",
        note="Без регистрации и рассылок",
    ),
    dict(
        name="План на выходные",
        title="Готовый план «Адыгея за выходные»",
        text="Два дня по часам: во сколько выезжать, где ночевать, что успеть и в каком порядке, чтобы не метаться. Выложил в клубе одним сообщением.",
        button_text="Посмотреть план",
        note="Он в закреплённых",
    ),
    dict(
        name="Транспорт без машины",
        title="Шпаргалка: как доехать без машины",
        text="Какие автобусы и маршрутки идут из Майкопа, откуда отправляются, сколько стоят и во сколько последний рейс обратно. Обновляю, когда меняется расписание.",
        button_text="Открыть шпаргалку",
        note="Обновляется каждый сезон",
    ),
    dict(
        name="Бюджет поездки",
        title="Сколько на самом деле стоит поездка в Адыгею",
        text="Разложил по статьям: жильё, еда, входы на тропы, бензин и трансферы — с реальными суммами, а не «от 5000 рублей». В закреплённых клуба.",
        button_text="Посмотреть расклад",
        note="Цифры с моих последних поездок",
    ),
]
with Session(engine) as _seed_db:
    if _seed_db.execute(select(func.count()).select_from(Magnet)).scalar() == 0:
        for _m in _DEFAULT_MAGNETS:
            _seed_db.add(Magnet(**_m))
        _seed_db.commit()

# Стартовый набор частых вопросов — дальше правится только через админку.
_DEFAULT_FAQ_SETS = [
    dict(
        slug="obshchie", name="Общие вопросы", title="Частые вопросы о поездке",
        on_faq_page=True, order_index=0,
        items=[
            {"question": "Когда лучше ехать в Адыгею?",
             "answer": "<p>С мая по сентябрь работают все пешие маршруты, включая высокогорные. Зимой плато закрыто снегом, но ущелья, пещеры и термальные источники работают круглый год — поездка не отменяется, просто меняется набор мест.</p>"},
            {"question": "Сколько дней закладывать?",
             "answer": "<p>Два дня — минимум, чтобы увидеть главное без спешки. За один день придётся выбирать между лёгкой прогулкой (теснина и водопады) и выездом на плато. Четыре-пять дней позволяют добавить Гузерипль и заповедник.</p>"},
            {"question": "Нужна ли машина?",
             "answer": "<p>Без машины реально посмотреть Хаджохскую теснину, водопады Руфабго и термальные источники — до них ходит рейсовый транспорт от Майкопа. На плато Лагонаки общественный транспорт не идёт, туда нужен трансфер или экскурсия.</p>"},
            {"question": "Сколько стоит вход на маршруты?",
             "answer": "<p>Большинство троп платные, но недорого — обычно несколько сотен рублей с человека. Цены меняются, поэтому конкретные суммы смотрите на страницах мест: там указана дата, на которую они актуальны.</p>"},
        ],
    ),
    dict(
        slug="s-detmi", name="С детьми", title="Вопросы про поездку с детьми",
        on_faq_page=True, order_index=1,
        items=[
            {"question": "С какого возраста можно везти ребёнка?",
             "answer": "<p>С малышами до 3-4 лет нормально проходятся Хаджохская теснина, термальные источники и первые водопады каскада Руфабго. Полный маршрут на плато и дальние точки каскада лучше отложить до школьного возраста.</p>"},
            {"question": "Пройдёт ли коляска?",
             "answer": "<p>По основным дорожкам Хаджохской теснины — да. На тропе к водопадам коляска будет только мешать: местами ступени, и ребёнка придётся нести на руках.</p>"},
        ],
    ),
]
with Session(engine) as _seed_db:
    if _seed_db.execute(select(func.count()).select_from(FaqSet)).scalar() == 0:
        for _f in _DEFAULT_FAQ_SETS:
            _seed_db.add(FaqSet(**_f))
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
    cover_thumb_url: Optional[str] = None
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
    cover_thumb_url: Optional[str] = None
    body: Optional[str] = None
    faq: Optional[List[FAQItemIn]] = None
    district: Optional[str] = None
    featured_checkpoint_ids: Optional[List[int]] = None
    featured_trail_ids: Optional[List[int]] = None
    is_published: Optional[bool] = None


class ScenarioIn(BaseModel):
    slug: Optional[str] = None
    icon: Optional[str] = None
    door: str
    hint: Optional[str] = None
    title: str
    lead: Optional[str] = None
    cover_url: Optional[str] = None
    cover_thumb_url: Optional[str] = None
    tile_cover_url: Optional[str] = None
    tile_cover_thumb_url: Optional[str] = None
    seo_description: Optional[str] = None
    featured_article_ids: List[int] = []
    # Три состояния — "any"/"yes"/"no" и "any"/"year_round"/"summer_only" —
    # а не Optional[bool]/Optional[str] со смыслом «не трогать поле»: форма в
    # админке всегда отправляет сценарий целиком, и если бы «неважно»
    # кодировалось как None, вернуть фильтр в «неважно» после того, как он
    # был выставлен, было бы нельзя (см. _apply_scenario).
    filter_kid_friendly: str = "any"     # any | yes | no
    filter_popularity: List[str] = []
    filter_difficulty: List[str] = []
    filter_seasonality: str = "any"      # any | year_round | summer_only
    filter_access: List[str] = []
    order_index: int = 0
    is_published: bool = True

class ScenarioUpdate(ScenarioIn):
    door: Optional[str] = None
    title: Optional[str] = None


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
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
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
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
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
        cover_thumb_url=body.cover_thumb_url,
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
    if body.cover_thumb_url is not None: a.cover_thumb_url = body.cover_thumb_url
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
        "cover_thumb_url": a.cover_thumb_url,
        "body": a.body,
        "faq": a.faq or [],
        "district": a.district,
        "featured_checkpoint_ids": a.featured_checkpoint_ids or [],
        "featured_trail_ids": a.featured_trail_ids or [],
        "is_published": a.is_published,
    }


# ─────────────────────────────────────────────
#  SCENARIOS — двери развилки на главной («Еду с детьми», «Без машины»...).
#  Места и маршруты внутри не хранятся списком — сайт сам подбирает их из
#  filter_*-полей на каждый рендер (site_app/router.py, _scenario_conditions).
# ─────────────────────────────────────────────

def _tri_to_kid(value: str) -> Optional[bool]:
    return {"yes": True, "no": False}.get(value)


def _tri_to_season(value: str) -> Optional[str]:
    return value if value in ("year_round", "summer_only") else None


def _apply_scenario(sc: Scenario, body: ScenarioIn):
    if body.door is not None: sc.door = body.door
    if body.title is not None: sc.title = body.title
    sc.icon = body.icon
    sc.hint = body.hint
    sc.lead = body.lead
    sc.cover_url = body.cover_url
    sc.cover_thumb_url = body.cover_thumb_url
    sc.tile_cover_url = body.tile_cover_url
    sc.tile_cover_thumb_url = body.tile_cover_thumb_url
    sc.seo_description = body.seo_description
    sc.featured_article_ids = body.featured_article_ids or []
    sc.filter_kid_friendly = _tri_to_kid(body.filter_kid_friendly)
    sc.filter_popularity = body.filter_popularity or []
    sc.filter_difficulty = body.filter_difficulty or []
    sc.filter_seasonality = _tri_to_season(body.filter_seasonality)
    sc.filter_access = body.filter_access or []
    sc.order_index = body.order_index
    sc.is_published = body.is_published


@app.get("/api/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    rows = db.execute(select(Scenario).order_by(Scenario.order_index, Scenario.id)).scalars().all()
    return [_scenario_out(s) for s in rows]


@app.post("/api/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    slug = _unique_slug(db, _slugify(body.slug or body.door), model=Scenario)
    sc = Scenario(slug=slug)
    _apply_scenario(sc, body)
    db.add(sc); db.commit(); db.refresh(sc)
    return _scenario_out(sc)


@app.patch("/api/scenarios/{scenario_id}")
def update_scenario(scenario_id: int, body: ScenarioUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    sc = _get_or_404(db, Scenario, scenario_id)
    if body.slug is not None:
        sc.slug = _unique_slug(db, _slugify(body.slug), exclude_id=scenario_id, model=Scenario)
    _apply_scenario(sc, body)
    db.commit(); db.refresh(sc)
    return _scenario_out(sc)


@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    sc = _get_or_404(db, Scenario, scenario_id)
    db.delete(sc); db.commit()
    return {"ok": True}


def _scenario_out(s: Scenario):
    return {
        "id": s.id,
        "slug": s.slug,
        "icon": s.icon,
        "door": s.door,
        "hint": s.hint,
        "title": s.title,
        "lead": s.lead,
        "cover_url": s.cover_url,
        "cover_thumb_url": s.cover_thumb_url,
        "tile_cover_url": s.tile_cover_url,
        "tile_cover_thumb_url": s.tile_cover_thumb_url,
        "seo_description": s.seo_description,
        "featured_article_ids": s.featured_article_ids or [],
        "filter_kid_friendly": {True: "yes", False: "no"}.get(s.filter_kid_friendly, "any"),
        "filter_popularity": s.filter_popularity or [],
        "filter_difficulty": s.filter_difficulty or [],
        "filter_seasonality": s.filter_seasonality or "any",
        "filter_access": s.filter_access or [],
        "order_index": s.order_index,
        "is_published": s.is_published,
    }


# ─────────────────────────────────────────────
#  БЛОКИ ДЛЯ СТАТЕЙ — лид-магниты и наборы вопросов.
#  Переиспользуемые: в теле статьи лежит только ссылка на id, содержимое
#  подставляется на рендере, поэтому правка блока обновляет все статьи разом.
# ─────────────────────────────────────────────

class MagnetIn(BaseModel):
    name: str
    title: str
    text: Optional[str] = None
    button_text: str = "Забрать в клубе"
    note: Optional[str] = None
    telegram_url: Optional[str] = None
    max_url: Optional[str] = None
    is_published: bool = True

class MagnetUpdate(MagnetIn):
    name: Optional[str] = None
    title: Optional[str] = None


class FaqItemIn(BaseModel):
    question: str
    answer: str

class FaqSetIn(BaseModel):
    name: str
    slug: Optional[str] = None
    title: Optional[str] = None
    items: List[FaqItemIn] = []
    on_faq_page: bool = False
    order_index: int = 0
    is_published: bool = True

class FaqSetUpdate(FaqSetIn):
    name: Optional[str] = None


def _magnet_out(m: Magnet):
    return {
        "id": m.id, "name": m.name, "title": m.title, "text": m.text,
        "button_text": m.button_text, "note": m.note,
        "telegram_url": m.telegram_url, "max_url": m.max_url,
        "is_published": m.is_published,
    }


@app.get("/api/magnets")
def list_magnets(db: Session = Depends(get_db)):
    rows = db.execute(select(Magnet).order_by(Magnet.id)).scalars().all()
    return [_magnet_out(m) for m in rows]


@app.post("/api/magnets", status_code=201)
def create_magnet(body: MagnetIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    m = Magnet(**body.model_dump())
    db.add(m); db.commit(); db.refresh(m)
    return _magnet_out(m)


@app.patch("/api/magnets/{magnet_id}")
def update_magnet(magnet_id: int, body: MagnetUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    m = _get_or_404(db, Magnet, magnet_id)
    for field, value in body.model_dump().items():
        if field in ("name", "title") and value is None:
            continue          # обязательные поля не затираем пустотой
        setattr(m, field, value)
    db.commit(); db.refresh(m)
    return _magnet_out(m)


@app.delete("/api/magnets/{magnet_id}")
def delete_magnet(magnet_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    m = _get_or_404(db, Magnet, magnet_id)
    db.delete(m); db.commit()
    return {"ok": True}


def _faq_set_out(f: FaqSet):
    return {
        "id": f.id, "slug": f.slug, "name": f.name, "title": f.title,
        "items": f.items or [], "on_faq_page": f.on_faq_page,
        "order_index": f.order_index, "is_published": f.is_published,
    }


@app.get("/api/faq-sets")
def list_faq_sets(db: Session = Depends(get_db)):
    rows = db.execute(select(FaqSet).order_by(FaqSet.order_index, FaqSet.id)).scalars().all()
    return [_faq_set_out(f) for f in rows]


@app.post("/api/faq-sets", status_code=201)
def create_faq_set(body: FaqSetIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    slug = _unique_slug(db, _slugify(body.slug or body.name), model=FaqSet)
    f = FaqSet(
        slug=slug, name=body.name, title=body.title,
        items=[i.model_dump() for i in body.items],
        on_faq_page=body.on_faq_page, order_index=body.order_index,
        is_published=body.is_published,
    )
    db.add(f); db.commit(); db.refresh(f)
    return _faq_set_out(f)


@app.patch("/api/faq-sets/{set_id}")
def update_faq_set(set_id: int, body: FaqSetUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    f = _get_or_404(db, FaqSet, set_id)
    if body.slug is not None:
        f.slug = _unique_slug(db, _slugify(body.slug), exclude_id=set_id, model=FaqSet)
    if body.name is not None: f.name = body.name
    f.title = body.title
    f.items = [i.model_dump() for i in body.items]
    f.on_faq_page = body.on_faq_page
    f.order_index = body.order_index
    f.is_published = body.is_published
    db.commit(); db.refresh(f)
    return _faq_set_out(f)


@app.delete("/api/faq-sets/{set_id}")
def delete_faq_set(set_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    f = _get_or_404(db, FaqSet, set_id)
    db.delete(f); db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────
#  PREVIEW — прогоняем несохранённый текст через тот же рендер, что и сайт,
#  чтобы предпросмотр в админке не разъезжался с реальной страницей.
# ─────────────────────────────────────────────

class PreviewIn(BaseModel):
    kind: str = "article"          # article | description
    html: str = ""


@app.post("/api/preview")
def render_preview(body: PreviewIn, _: bool = Depends(require_admin)):
    from site_app.router import _add_toc_anchors, _render_article_gallery, _render_consider_blocks, _rich_text_html

    rendered = _render_consider_blocks(_rich_text_html(body.html))
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
