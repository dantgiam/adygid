import io
import os
import secrets
import uuid
from datetime import datetime
from html import escape as _esc_html
from typing import Optional, List

import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select, func, text
from geoalchemy2.shape import to_shape
from shapely.geometry import shape, mapping
from pydantic import BaseModel
from PIL import Image, ImageOps

from app.database import Base, engine, get_db
from app.models import (
    Trail, TrailSegment, Checkpoint, Photo, Category, Article, Like, Scenario,
    Magnet, FaqSet, SitePage, DifficultyLevel, District,
)
from app.slugs import slugify as _slugify, unique_slug as _unique_slug
from site_app.content import (
    DIFFICULTY_INFO as _DIFFICULTY_SEED,
    DISTRICTS as _DISTRICT_NAMES_SEED,
    DISTRICT_PAGES as _DISTRICT_PAGES_SEED,
    consider_embed_html,
)
from site_app.router import router as site_router

app = FastAPI(title="АдыГид API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Иконки, которые браузеры и поисковые роботы запрашивают из корня домена, —
# такая же неизменная статика, как содержимое /assets, и кэшируется наравне.
_ROOT_ICON_PATHS = frozenset({
    "/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png",
})


@app.middleware("http")
async def _cache_policy(request, call_next):
    """HTML не кэшируем — проект активно меняется, и правки должны быть видны
    сразу. А вот статика (стикеры почти на мегабайт, стили, скрипты, фото)
    раньше тоже отдавалась с no-store, и браузер перекачивал её при каждом
    переходе между страницами — именно это делало навигацию медленной."""
    response = await call_next(request)
    path = request.url.path

    # Любой не-GET запрос — это правка через админку (или лайк, который тоже
    # виден на главной). Сбрасываем готовый HTML главной здесь, одним местом,
    # вместо того чтобы дёргать сброс из двух десятков эндпоинтов по отдельности.
    # Именно после call_next: до него правка ещё не записана, и параллельный
    # заход на главную успел бы закэшировать старое содержимое заново.
    if request.method != "GET":
        from site_app.router import invalidate_home_cache
        invalidate_home_cache()
    # Стили и скрипты сайта подключаются с ?v=<версия>, фото загружаются под
    # уникальными именами — их можно смело кэшировать надолго. Файлы админки
    # сюда не попадают: она правится часто, а открывает её один человек.
    if path.startswith("/assets/") or path.startswith("/static/uploads/") \
            or path in _ROOT_ICON_PATHS:
        response.headers["Cache-Control"] = "public, max-age=604800"
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


# Текст страниц сжимается — HTML со списками карточек ужимается в несколько раз
app.add_middleware(GZipMiddleware, minimum_size=800)


# Служебные ветки, которым нужен машинный ответ: админка ходит в /api и разбирает
# JSON, статика отдаётся файловым мидлварём. Всё остальное запрашивает человек
# браузером — ему показываем нормальную страницу, а не {"detail": "..."}.
_JSON_ERROR_PREFIXES = ("/api/", "/static/", "/assets/")


@app.exception_handler(StarletteHTTPException)
async def _not_found_page(request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith(_JSON_ERROR_PREFIXES):
        from site_app.router import render_not_found
        return render_not_found(request)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

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
        _conn.execute(text(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS checked_at TIMESTAMP"))
        _conn.execute(text(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT true"))
    _conn.execute(text("ALTER TABLE photos ADD COLUMN IF NOT EXISTS caption VARCHAR(255)"))
    # Точка фокуса кадра — что именно оставить в кадре, когда обложка обрезается
    # под формат карточки. Хранится готовым значением object-position («50% 30%»),
    # пусто — центр, как было до появления настройки.
    _conn.execute(text("ALTER TABLE photos ADD COLUMN IF NOT EXISTS focus VARCHAR(20)"))
    _conn.execute(text("ALTER TABLE articles ADD COLUMN IF NOT EXISTS cover_focus VARCHAR(20)"))
    _conn.execute(text("ALTER TABLE districts ADD COLUMN IF NOT EXISTS cover_focus VARCHAR(20)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS cover_focus VARCHAR(20)"))
    _conn.execute(text("ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS tile_cover_focus VARCHAR(20)"))

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

# Шкала сложности — засевается один раз из прежней константы DIFFICULTY_INFO.
# Дальше источник истины — таблица, её правят в админке, и повторный старт
# уже заведённые уровни не трогает.
with Session(engine) as _seed_db:
    _have = {row[0] for row in _seed_db.execute(select(DifficultyLevel.code)).all()}
    for _i, (_code, _info) in enumerate(_DIFFICULTY_SEED.items()):
        if _code in _have:
            continue
        _seed_db.add(DifficultyLevel(
            code=_code, title=_info["title"], text=_info["text"],
            color=_info["color"], dots=_info["dots"], order_index=_i,
        ))
    _seed_db.commit()

# Округа — переносим из констант content.py один раз. Дальше источник истины
# таблица: там же правятся название, вступление, факты и обложка.
with Session(engine) as _seed_db:
    _have = {row[0] for row in _seed_db.execute(select(District.slug)).all()}
    for _i, (_slug, _name) in enumerate(_DISTRICT_NAMES_SEED.items()):
        if _slug in _have:
            continue
        _page = _DISTRICT_PAGES_SEED.get(_slug, {})
        _seed_db.add(District(
            slug=_slug, name=_name, lead=_page.get("lead"),
            facts=_page.get("facts", []), order_index=_i,
        ))
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

# Тексты шапки главной и страницы клуба — раньше жили прямо в HTML-шаблоне,
# теперь читаются из БД и правятся в админке. Засеваются один раз тем же
# текстом, что раньше был зашит в шаблон, — на сайте ничего не меняется,
# пока автор сам не отредактирует.
_DEFAULT_SITE_PAGES = [
    dict(
        slug="home", eyebrow="Привет", title="Адыгея? АдыГид!",
        lead="Здесь вы найдёте ответы на главные вопросы поездки — что посетить, сколько времени закладывать, где заночевать и что успеть увидеть за день-два. Все места и маршруты я прошёл сам и описал их для вас максимально подробно.",
        lead_extra="Ни один вариант не подошёл?",
    ),
    dict(
        slug="difficulty", title="Что означают уровни сложности",
        lead="Сложность — это про физическую нагрузку и рельеф, а не про опасность. Ориентируйтесь на неё, когда решаете, брать ли с собой детей и какую обувь надеть.",
    ),
    dict(
        slug="club", eyebrow="Сообщество", title="Клуб АдыГид в MAX",
        lead="Отзывы, живые впечатления и общение с теми, кто уже был в Адыгее или только планирует поездку. Здесь можно спросить про погоду на плато на конкретной неделе, состояние дороги, актуальные цены на входы — то, что быстро устаревает в любых описаниях.",
        lead_extra="Вступление свободное, ничего платить не нужно.",
        button_text="Вступить в клуб в MAX →",
    ),
]
with Session(engine) as _seed_db:
    _existing_page_slugs = {row[0] for row in _seed_db.execute(select(SitePage.slug)).all()}
    for _sp in _DEFAULT_SITE_PAGES:
        if _sp["slug"] not in _existing_page_slugs:
            _seed_db.add(SitePage(**_sp))
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
# Обложка карточки — примерно 357 px шириной, на retina это 714.
# Прежние 480 px давали заметное мыло на телефонах и ноутбуках.
THUMB_SIZE = (800, 800)
# Потолок для «оригинала»: под обложку детальной страницы с запасом на retina.
MAX_IMAGE_SIZE = (1920, 1920)
WEBP_QUALITY = 82
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
    out_ext, content_type = ext, CONTENT_TYPES[ext]

    thumb_data = data
    try:
        img = Image.open(io.BytesIO(data))
        # Телефон часто пишет кадр «как держали» и кладёт нужный поворот в EXIF
        # Orientation, а не в сами пиксели. exif_transpose впечатывает поворот
        # в пиксели один раз здесь — иначе он теряется при пересжатии миниатюры
        # (Pillow не переносит EXIF в .save()) и превью показывает сырой кадр
        # боком: широкое фото на обложке карточки вдруг становится вертикальным.
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Кадр с телефона — это 4000×3000 и мегабайты, а самое крупное место на
        # сайте под фото — обложка детальной страницы, меньше 1600 CSS px даже
        # на большом мониторе. Раньше оригинал уходил в хранилище как есть, и
        # человек с телефона качал 5 МБ ради картинки в 460 px высотой.
        img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)

        # WebP независимо от исходного формата: он и сам по себе легче JPEG,
        # и снимает главную беду PNG — рисованная обложка в PNG весила 357 КБ
        # даже в виде миниатюры 480 px, в WebP тот же кадр занимает 41 КБ.
        out_ext, content_type = "webp", CONTENT_TYPES["webp"]
        orig_buf = io.BytesIO()
        img.save(orig_buf, "WEBP", quality=WEBP_QUALITY, method=6)
        data = orig_buf.getvalue()

        thumb_img = img.copy()
        thumb_img.thumbnail(THUMB_SIZE)
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, "WEBP", quality=WEBP_QUALITY, method=6)
        thumb_data = thumb_buf.getvalue()
    except Exception:
        # Не смогли разобрать картинку — кладём файл как прислали, без потерь
        pass

    orig_object = f"{name}.{out_ext}"
    thumb_object = f"{name}_thumb.{out_ext}"
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
    checked_at: Optional[datetime] = None
    is_published: bool = True

class TrailUpdate(ExtraCriteriaIn):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    duration_minutes: Optional[int] = None
    checked_at: Optional[datetime] = None
    is_published: Optional[bool] = None

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
    checked_at: Optional[datetime] = None
    is_published: bool = True
    lon: float
    lat: float

class CheckpointUpdate(ExtraCriteriaIn):
    # trail_id разбирается через model_fields_set: null здесь — осмысленное
    # значение («отвязать от маршрута»), а не «поле не прислали».
    trail_id: Optional[int] = None
    name: Optional[str] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    order_index: Optional[int] = None
    duration_minutes: Optional[int] = None
    show_as_place: Optional[bool] = None
    checked_at: Optional[datetime] = None
    is_published: Optional[bool] = None
    lon: Optional[float] = None
    lat: Optional[float] = None

class CheckpointOrderIn(BaseModel):
    """Новый порядок точек маршрута — список id в нужной последовательности."""
    ids: List[int]

class PhotoIn(BaseModel):
    url: str
    thumb_url: Optional[str] = None
    caption: Optional[str] = None

class PhotoUpdate(BaseModel):
    caption: Optional[str] = None
    focus: Optional[str] = None

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
    cover_focus: Optional[str] = None
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
    cover_focus: Optional[str] = None
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
    cover_focus: Optional[str] = None
    tile_cover_url: Optional[str] = None
    tile_cover_thumb_url: Optional[str] = None
    tile_cover_focus: Optional[str] = None
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


@app.get("/api/trails/{trail_id}")
def get_trail(trail_id: int, db: Session = Depends(get_db)):
    """Один маршрут целиком. Редактору карты после каждой правки нужна только
    свежая геометрия — тянуть ради этого весь список маршрутов незачем."""
    return _trail_out(_get_or_404(db, Trail, trail_id))


@app.post("/api/trails", status_code=201)
def create_trail(body: TrailIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    t = Trail(
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        duration_minutes=body.duration_minutes,
        checked_at=body.checked_at,
        is_published=body.is_published,
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
    if body.checked_at is not None:        t.checked_at = body.checked_at
    if body.is_published is not None:      t.is_published = body.is_published
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
        "checked_at": t.checked_at.isoformat() if t.checked_at else None,
        "is_published": t.is_published,
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
        checked_at=body.checked_at,
        is_published=body.is_published,
        geom=f"SRID=4326;POINT({body.lon} {body.lat})",
        **_extra_criteria_kwargs(body),
    )
    db.add(cp); db.commit(); db.refresh(cp)
    return _cp_out(cp)


@app.patch("/api/checkpoints/{cp_id}")
def update_checkpoint(cp_id: int, body: CheckpointUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    cp = _get_or_404(db, Checkpoint, cp_id)
    if "trail_id" in body.model_fields_set and body.trail_id != cp.trail_id:
        if body.trail_id is None:
            # Отвязали от маршрута — точка остаётся, но живёт сама по себе,
            # а значит должна быть видна на сайте как место.
            cp.trail_id = None
            cp.order_index = 0
            cp.show_as_place = True
        else:
            _get_or_404(db, Trail, body.trail_id)
            cp.trail_id = body.trail_id
            last = db.execute(
                select(func.max(Checkpoint.order_index)).where(Checkpoint.trail_id == body.trail_id)
            ).scalar()
            cp.order_index = 0 if last is None else last + 1
    if body.name is not None:        cp.name = body.name
    if body.category_id is not None: cp.category_id = body.category_id
    if body.description is not None: cp.description = body.description
    if body.order_index is not None: cp.order_index = body.order_index
    if body.duration_minutes is not None: cp.duration_minutes = body.duration_minutes
    if body.show_as_place is not None: cp.show_as_place = body.show_as_place
    if body.checked_at is not None:  cp.checked_at = body.checked_at
    if body.is_published is not None: cp.is_published = body.is_published
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


@app.patch("/api/photos/{photo_id}")
def update_photo(photo_id: int, body: PhotoUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    photo = _get_or_404(db, Photo, photo_id)
    if body.caption is not None: photo.caption = body.caption
    if body.focus is not None: photo.focus = body.focus or None
    db.commit(); db.refresh(photo)
    return _photo_out(photo)


@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    photo = _get_or_404(db, Photo, photo_id)
    _delete_uploaded_files(photo)
    db.delete(photo); db.commit()
    return {"ok": True}


def _photo_out(p: Photo):
    return {"id": p.id, "url": p.url, "thumb_url": p.thumb_url, "caption": p.caption, "focus": p.focus}


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
        "checked_at": c.checked_at.isoformat() if c.checked_at else None,
        "is_published": c.is_published,
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
        cover_focus=body.cover_focus,
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
    if body.cover_focus is not None: a.cover_focus = body.cover_focus or None
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
        "cover_focus": a.cover_focus,
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
    sc.cover_focus = body.cover_focus or None
    sc.tile_cover_url = body.tile_cover_url
    sc.tile_cover_thumb_url = body.tile_cover_thumb_url
    sc.tile_cover_focus = body.tile_cover_focus or None
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
        "cover_focus": s.cover_focus,
        "tile_cover_url": s.tile_cover_url,
        "tile_cover_thumb_url": s.tile_cover_thumb_url,
        "tile_cover_focus": s.tile_cover_focus,
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
#  СТРАНИЦЫ САЙТА — тексты шапки главной и страницы клуба. Обе строки
#  засеяны при первом старте (см. выше) и всегда существуют, поэтому здесь
#  только чтение и правка — ни создания, ни удаления не требуется.
# ─────────────────────────────────────────────

class SitePageUpdate(BaseModel):
    eyebrow: Optional[str] = None
    title: Optional[str] = None
    lead: Optional[str] = None
    lead_extra: Optional[str] = None
    button_text: Optional[str] = None


def _site_page_out(p: SitePage) -> dict:
    return {
        "slug": p.slug,
        "eyebrow": p.eyebrow,
        "title": p.title,
        "lead": p.lead,
        "lead_extra": p.lead_extra,
        "button_text": p.button_text,
    }


@app.get("/api/site-pages")
def list_site_pages(db: Session = Depends(get_db)):
    rows = db.execute(select(SitePage).order_by(SitePage.id)).scalars().all()
    return [_site_page_out(p) for p in rows]


@app.patch("/api/site-pages/{slug}")
def update_site_page(slug: str, body: SitePageUpdate, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    p = db.execute(select(SitePage).where(SitePage.slug == slug)).scalars().first()
    if not p:
        raise HTTPException(404, "Страница не найдена")
    p.eyebrow = body.eyebrow
    p.title = body.title
    p.lead = body.lead
    p.lead_extra = body.lead_extra
    p.button_text = body.button_text
    db.commit()
    db.refresh(p)
    return _site_page_out(p)


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


class DistrictIn(BaseModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    lead: Optional[str] = None
    facts: Optional[List[str]] = None
    cover_url: Optional[str] = None
    cover_thumb_url: Optional[str] = None
    cover_focus: Optional[str] = None
    order_index: Optional[int] = None
    is_published: Optional[bool] = None


def _district_out(d: District) -> dict:
    return {
        "id": d.id, "slug": d.slug, "name": d.name, "lead": d.lead or "",
        "facts": d.facts or [], "cover_url": d.cover_url, "cover_thumb_url": d.cover_thumb_url,
        "cover_focus": d.cover_focus,
        "order_index": d.order_index, "is_published": d.is_published,
    }


@app.get("/api/districts")
def list_districts(db: Session = Depends(get_db)):
    rows = db.execute(select(District).order_by(District.order_index, District.id)).scalars().all()
    return [_district_out(d) for d in rows]


@app.post("/api/districts", status_code=201)
def create_district(body: DistrictIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    slug = (body.slug or _slugify(body.name or "")).strip()
    if not slug or not body.name:
        raise HTTPException(400, "Нужны название и адрес округа")
    if db.execute(select(District).where(District.slug == slug)).scalars().first():
        raise HTTPException(400, "Округ с таким адресом уже есть")
    d = District(
        slug=slug, name=body.name, lead=body.lead, facts=body.facts or [],
        cover_url=body.cover_url, cover_thumb_url=body.cover_thumb_url, cover_focus=body.cover_focus,
        order_index=body.order_index or 0,
        is_published=True if body.is_published is None else body.is_published,
    )
    db.add(d); db.commit(); db.refresh(d)
    return _district_out(d)


@app.patch("/api/districts/{district_id}")
def update_district(district_id: int, body: DistrictIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    d = _get_or_404(db, District, district_id)
    # slug намеренно не меняем: он записан в district у мест, маршрутов и статей,
    # и правка здесь молча оторвала бы их все от округа.
    if body.name is not None: d.name = body.name
    if body.lead is not None: d.lead = body.lead
    if body.facts is not None: d.facts = body.facts
    if body.cover_url is not None: d.cover_url = body.cover_url or None
    if body.cover_thumb_url is not None: d.cover_thumb_url = body.cover_thumb_url or None
    if body.cover_focus is not None: d.cover_focus = body.cover_focus or None
    if body.order_index is not None: d.order_index = body.order_index
    if body.is_published is not None: d.is_published = body.is_published
    db.commit()
    return _district_out(d)


@app.delete("/api/districts/{district_id}", status_code=204)
def delete_district(district_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    d = _get_or_404(db, District, district_id)
    used = db.execute(
        select(func.count()).select_from(Checkpoint).where(Checkpoint.district == d.slug)
    ).scalar() or 0
    if used:
        raise HTTPException(400, f"К округу привязано мест: {used}. Сначала перенесите их в другой округ.")
    db.delete(d); db.commit()


class DifficultyIn(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    color: Optional[str] = None


def _difficulty_out(d: DifficultyLevel) -> dict:
    return {"code": d.code, "title": d.title, "text": d.text, "color": d.color, "dots": d.dots}


@app.get("/api/difficulty-levels")
def list_difficulty_levels(db: Session = Depends(get_db)):
    rows = db.execute(select(DifficultyLevel).order_by(DifficultyLevel.order_index)).scalars().all()
    return [_difficulty_out(d) for d in rows]


@app.patch("/api/difficulty-levels/{code}")
def update_difficulty_level(code: str, body: DifficultyIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    d = db.execute(select(DifficultyLevel).where(DifficultyLevel.code == code)).scalars().first()
    if not d:
        raise HTTPException(404, "Уровень не найден")
    if body.title is not None: d.title = body.title.strip() or d.title
    if body.text is not None: d.text = body.text.strip() or d.text
    if body.color is not None: d.color = body.color.strip() or d.color
    db.commit()
    return _difficulty_out(d)


@app.post("/api/preview")
def render_preview(body: PreviewIn, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    from site_app.router import _add_toc_anchors, _render_article_gallery, _render_embeds, _rich_text_html

    # Место/маршрут/сценарий вставляют коллажи и лид-магниты тем же редактором,
    # что и статья (см. descEditorHtml в admin.js) — раньше здесь разворачивался
    # только «Что учесть», и коллаж в предпросмотре так и оставался рядом
    # обычных картинок, а не галереей.
    rendered = _render_article_gallery(_rich_text_html(body.html))
    rendered, _faq = _render_embeds(db, rendered)
    if body.kind == "article":
        rendered, _toc = _add_toc_anchors(rendered)
    return {"html": rendered}


# ─────────────────────────────────────────────
#  STATIC
# ─────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="site_app/static"), name="site_static")
app.include_router(site_router)


# Иконки сайта лежат в /assets, но и поисковики, и браузеры первым делом
# спрашивают их в корне домена — без этих двух маршрутов /favicon.ico отдавал
# 404, и в выдаче рядом с сайтом рисовался серый глобус вместо кота.
@app.get("/favicon.ico", include_in_schema=False)
def favicon_root():
    return FileResponse("site_app/static/favicon.ico", media_type="image/x-icon")


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon_root():
    return FileResponse("site_app/static/apple-touch-icon.png", media_type="image/png")


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
