"""Точечные правки контента в базе, которые повторяются на каждом старте
и ничего не делают, если уже применены или данные не те (проверка по
названиям, а не только по id).

Маршрут «Уна-Коз понизу»: в описании были ссылки на /mesta/95, 96, 97 —
это точки маршрута без своей страницы, ссылки отдавали 404. Две из них
совпадают с настоящими карточками мест: верхняя станция → «Савранская
канатная дорога», выход к Чёртову пальцу → «Скала Чёртов палец». Третья
(вход в пещеру Пыльную) отдельной карточки не имеет — её ссылку при выводе
страницы site_app/urls.py ведёт на точку в списке маршрута (#stop-96).
"""
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models import Category, Checkpoint, Trail

# (маршрут, начало названия точки, точное название карточки места)
_STOP_TO_PLACE = [
    ("Уна-Коз понизу", "Старт: верхняя станция Савранской канатной дороги", "Савранская канатная дорога"),
    ("Уна-Коз понизу", "Выход к Чёртову пальцу", "Скала Чёртов палец"),
]


def fix_stop_links(db: Session) -> int:
    changed = 0
    for trail_prefix, stop_name, place_name in _STOP_TO_PLACE:
        place = db.execute(select(Checkpoint).where(
            Checkpoint.name == place_name, Checkpoint.show_as_place == True, Checkpoint.is_published == True,
        )).scalars().first()
        if not place:
            continue
        for t in db.execute(select(Trail).where(Trail.name.startswith(trail_prefix))).scalars().all():
            for cp in t.checkpoints:
                if cp.show_as_place or not cp.name.startswith(stop_name):
                    continue
                old = f'href="/mesta/{cp.id}"'
                if t.description and old in t.description:
                    # Без onupdate: это ремонт ссылки, а не правка маршрута.
                    db.execute(Trail.__table__.update().where(Trail.id == t.id).values(
                        description=t.description.replace(old, f'href="/mesta/{place.id}"'),
                        updated_at=Trail.__table__.c.updated_at,
                    ))
                    db.refresh(t)
                    changed += 1
    return changed


def apply(engine) -> int:
    with Session(engine) as db:
        n = fix_stop_links(db)
        db.commit()
    return n


# Карточка 30. Слаг не трогаем: адрес страницы остаётся прежним,
# отдельного URL не появляется. Подмена только если название и SEO-title
# всё ещё равны старому тексту — правка из админки не затирается.
MONASTERY_ID = 30
MONASTERY_OLD_NAME = "Михайло-Афонская пустынь"
MONASTERY_NAME = "Свято-Михайловский монастырь (Михайло-Афонская пустынь)"
MONASTERY_OLD_TITLE = "Михайло-Афонская пустынь: подземный монастырь и Физиабго — АдыГид"

# Белореченский водопад. Координата — узел OSM waterway=waterfall
# (node/11346662491, 27.09.2025): 44.7342467, 39.8775977.
# Административно Nominatim относит точку к Южненскому сельскому
# поселению Белореченского района Краснодарского края, не к станице
# Белореченская в Адыгее. Черновик: на сайте не показывается.
WATERFALL_NAME = "Белореченский водопад"
WATERFALL_SLUG = "belorechenskiy-vodopad"
WATERFALL_LAT = 44.7342467
WATERFALL_LON = 39.8775977
WATERFALL_OSM_NODE = "11346662491"
WATERFALL_DESCRIPTION = (
    "<p>Белореченский водопад — порог на реке Белой в Южненском сельском "
    "поселении Белореченского района Краснодарского края, рядом с городом "
    "Белореченск. Это Краснодарский край, не станица Белореченская "
    "Майкопского района Республики Адыгея.</p>"
    "<p>На OpenStreetMap точка подписана «Белореченский водопад» "
    "(waterway=waterfall): 44.7342467° с.ш., 39.8775977° в.д. "
    '<a href="https://www.openstreetmap.org/node/11346662491" rel="noopener">узел OSM</a>.</p>'
    "<p>По заметке «Кубанских новостей» от 17 августа 2025 года каскад на "
    "реке Белой в Белореченском районе появился за пару лет до публикации: "
    "вода ушла в карстовую пещеру. Пеший путь, который описывает заметка, "
    "начинается в городе Белореченске от остановки «База Эльна», дальше по "
    "улице Тополиной к грунтовой дороге и тропе через лес к реке. Основной "
    "слив — в начале речного каньона, по левому краю есть каскады поменьше. "
    '<a href="https://kubnews.ru/turizm/2025/08/17/v-krasnodarskom-krae-otkryli-turmarshrut-na-belorechenskiy-vodopad/" rel="noopener">«Кубанские новости»</a>.</p>'
    "<p>Режим работы, плату за вход и длину подхода карточка не указывает: "
    "в этих источниках нет официального расписания и прайса.</p>"
    "<p><strong>Заметки автора сайта</strong> (не из опубликованного источника): "
    "тропа глинистая, нужна обувь с хорошим протектором; в сезон дождей воды много.</p>"
)


def rename_mikhailovsky(db: Session) -> bool:
    """H1 и SEO-title карточки 30. Слаг не меняется. True, если что-то записали."""
    from site_app.seo import PLACE_TITLES

    changed = False
    cp = db.get(Checkpoint, MONASTERY_ID)
    if cp is not None and (cp.name or "").strip() == MONASTERY_OLD_NAME:
        cp.name = MONASTERY_NAME
        changed = True
    new_title = PLACE_TITLES[MONASTERY_ID]
    res = db.execute(text(
        "UPDATE place_trip_blocks SET seo_title = :new, updated_at = now() "
        "WHERE place_id = :pid AND seo_title = :old"
    ), {"new": new_title, "old": MONASTERY_OLD_TITLE, "pid": MONASTERY_ID})
    if res.rowcount:
        changed = True
    return changed


def seed_waterfall(db: Session) -> bool:
    """Черновик карточки. Повторный старт ничего не перезаписывает."""
    marker = Checkpoint.description.contains(WATERFALL_OSM_NODE)
    existing = db.execute(select(Checkpoint.id).where(or_(
        Checkpoint.name == WATERFALL_NAME,
        Checkpoint.slug == WATERFALL_SLUG,
        marker,
    ))).first()
    if existing:
        return False
    cat = db.execute(select(Category).where(Category.name == "Водопад")).scalars().first()
    db.add(Checkpoint(
        name=WATERFALL_NAME,
        slug=WATERFALL_SLUG,
        category_id=cat.id if cat else None,
        description=WATERFALL_DESCRIPTION,
        geom=f"SRID=4326;POINT({WATERFALL_LON} {WATERFALL_LAT})",
        show_as_place=True,
        is_published=False,
        is_paid=None,
        district=None,
    ))
    return True


def apply_editorial(engine) -> None:
    """После таблиц текстов: SEO-title карточки 30 уже мог быть скопирован из кода.

    Черновик водопада в тестовой базе не создаём: у него честно пустая
    стоимость (is_paid IS NULL), а тест старой схемы временно ставит
    NOT NULL на всю колонку. Сам тест карточки вызывает seed_waterfall.
    """
    import os

    from site_app import trip_facts

    testing = "adygid_test" in os.environ.get("DATABASE_URL", "")
    with Session(engine) as db:
        rename_mikhailovsky(db)
        if not testing:
            seed_waterfall(db)
        db.commit()
    trip_facts.invalidate()
