"""
Разовый скрипт с демо-контентом для нового сайта — несколько реальных мест,
маршрутов и статей, чтобы сайт не был пустым при первом запуске.

Координаты приблизительные (по общедоступным картам), названия и факты — из
открытых источников про Адыгею. Это стартовый черновик: поправьте описания,
цены и точные GPS-точки через админку на свой вкус.

Запуск (один раз, безопасно повторять — пропускает уже существующее по имени):
    docker compose exec api python seed_demo.py
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Article, Category, Checkpoint, Trail
from app.slugs import slugify, unique_slug

def cat(db, name):
    return db.execute(select(Category).where(Category.name == name)).scalars().first()


def get_or_create_checkpoint(db, name, **kwargs):
    existing = db.execute(select(Checkpoint).where(Checkpoint.name == name)).scalars().first()
    if existing:
        return existing
    lon = kwargs.pop("lon")
    lat = kwargs.pop("lat")
    cp = Checkpoint(name=name, geom=f"SRID=4326;POINT({lon} {lat})", **kwargs)
    db.add(cp)
    db.flush()
    return cp


def get_or_create_trail(db, name, **kwargs):
    existing = db.execute(select(Trail).where(Trail.name == name)).scalars().first()
    if existing:
        return existing
    t = Trail(name=name, **kwargs)
    db.add(t)
    db.flush()
    return t


def get_or_create_article(db, title, **kwargs):
    existing = db.execute(select(Article).where(Article.title == title)).scalars().first()
    if existing:
        return existing
    slug = unique_slug(db, slugify(title))
    a = Article(title=title, slug=slug, **kwargs)
    db.add(a)
    db.flush()
    return a


def run():
    with Session(engine) as db:
        c_waterfall = cat(db, "Водопад")
        c_canyon = cat(db, "Каньон / ущелье")
        c_cave = cat(db, "Пещера")
        c_plateau = cat(db, "Плато / гора")
        c_dolmen = cat(db, "Дольмен")
        c_thermal = cat(db, "Термальный источник")
        c_lake = cat(db, "Река / озеро")
        c_monastery = cat(db, "Монастырь / храм")
        c_hiking = cat(db, "Пеший")

        # ── Места ──────────────────────────────────────────────
        khadzhokh_gorge = get_or_create_checkpoint(
            db, "Хаджохская теснина", lon=40.1735, lat=44.1505,
            category_id=c_canyon.id if c_canyon else None,
            description=(
                "Узкое скальное ущелье реки Белой прямо у посёлка Каменномостский (Хаджох) — "
                "одно из самых доступных и посещаемых мест Адыгеи, буквально в шаге от дороги. "
                "Оборудованные мостики и смотровые позволяют пройти теснину за 30-40 минут."
            ),
            district="khadzhokh", popularity="top", is_paid=True, price_note="~300₽ с человека",
            kid_friendly=True, access_type="paved", duration_minutes=40,
        )

        azishskaya_cave = get_or_create_checkpoint(
            db, "Большая Азишская пещера", lon=40.0235, lat=44.0480,
            category_id=c_cave.id if c_cave else None,
            description=(
                "Одна из немногих карстовых пещер Адыгеи, оборудованных для массового посещения — "
                "с подсветкой и дорожками. Экскурсия проходит с гидом, около 40 минут под землёй."
            ),
            district="lagonaki", popularity="popular", is_paid=True, price_note="~400₽ с человека",
            access_type="high_clearance", duration_minutes=45,
        )

        lagonaki_plateau = get_or_create_checkpoint(
            db, "Плато Лаго-Наки", lon=40.0100, lat=44.0100,
            category_id=c_plateau.id if c_plateau else None,
            description=(
                "Высокогорное плато с альпийскими лугами, карстовыми воронками и снежниками, "
                "которые не тают даже летом. Точка входа во множество треккинговых маршрутов, "
                "включая подходы к горам Фишт и Оштен."
            ),
            district="lagonaki", popularity="top", seasonality="summer_only",
            access_type="high_clearance", duration_minutes=240,
        )

        guzeripl_dolmen = get_or_create_checkpoint(
            db, "Дольмен у Гузерипля", lon=40.0870, lat=44.1530,
            category_id=c_dolmen.id if c_dolmen else None,
            description=(
                "Мегалитическая гробница возрастом несколько тысяч лет — один из самых доступных "
                "дольменов Адыгеи, у самого посёлка Гузерипль, на границе Кавказского заповедника."
            ),
            district="guzeripl", popularity="normal", access_type="foot_only", duration_minutes=20,
        )

        thermal_tulsky = get_or_create_checkpoint(
            db, "Термальный комплекс в Тульском", lon=40.0960, lat=44.5170,
            category_id=c_thermal.id if c_thermal else None,
            description=(
                "Бассейны с горячей минеральной водой из скважины — популярное место отдыха "
                "рядом с Майкопом, работает круглый год, отдельные бассейны разной температуры."
            ),
            district="maikop", popularity="popular", is_paid=True, price_note="от 500₽/час",
            seasonality="year_round", access_type="paved", kid_friendly=True, duration_minutes=90,
        )

        psenodah_lake = get_or_create_checkpoint(
            db, "Озеро Псенодах", lon=40.0350, lat=43.9700,
            category_id=c_lake.id if c_lake else None,
            description=(
                "Горное озеро в форме полумесяца на территории Кавказского биосферного заповедника — "
                "добраться можно только пешим многодневным переходом, требуется пропуск в заповедник."
            ),
            district="guzeripl", popularity="normal", difficulty="hard",
            access_type="foot_only", seasonality="summer_only",
        )

        monastery = get_or_create_checkpoint(
            db, "Михайло-Афонская пустынь", lon=40.1600, lat=44.1600,
            category_id=c_monastery.id if c_monastery else None,
            description=(
                "Действующий мужской монастырь конца XIX века недалеко от Каменномостского, "
                "с смотровой площадкой и источником — тихое место для остановки по пути к теснине."
            ),
            district="khadzhokh", popularity="normal", access_type="high_clearance", duration_minutes=40,
        )

        rufabgo_trail = get_or_create_trail(
            db, "Водопады Руфабго", category_id=c_hiking.id if c_hiking else None,
            description=(
                "Прогулочный маршрут вдоль ручья Руфабго к каскаду из нескольких водопадов в буковом "
                "лесу — один из самых популярных маршрутов Адыгеи, тропа оборудована и не требует "
                "подготовки."
            ),
            district="khadzhokh", popularity="top", difficulty="easy", duration_minutes=150,
            is_paid=True, price_note="~400₽ с человека", kid_friendly=True, access_type="foot_only",
        )
        rufabgo_shum = get_or_create_checkpoint(
            db, "Водопад Шум (Руфабго)", lon=40.1610, lat=44.1560,
            category_id=c_waterfall.id if c_waterfall else None, trail_id=rufabgo_trail.id, order_index=0,
            description="Первый и самый мощный водопад каскада Руфабго, сразу за входом на тропу.",
            district="khadzhokh", popularity="top", is_paid=True, kid_friendly=True,
        )
        rufabgo_small = get_or_create_checkpoint(
            db, "Малый Руфабго", lon=40.1625, lat=44.1545,
            category_id=c_waterfall.id if c_waterfall else None, trail_id=rufabgo_trail.id, order_index=1,
            description="Один из верхних водопадов каскада, тише и малолюднее первого.",
            district="khadzhokh", popularity="normal", is_paid=True, kid_friendly=True,
        )

        lagonaki_trail = get_or_create_trail(
            db, "Плато Лагонаки — маршрут одного дня", category_id=c_hiking.id if c_hiking else None,
            description=(
                "Дневной пеший выход на плато Лагонаки — альпийские луга, карстовые воронки, "
                "виды на Фишт и Оштен. Требует хорошей физической подготовки и трансфера с "
                "клиренсом до начала тропы."
            ),
            district="lagonaki", popularity="popular", difficulty="hard", duration_minutes=360,
            access_type="high_clearance", seasonality="summer_only",
            equipment_tags=["треккинговые палки", "ветровка", "запас воды"],
        )
        db.flush()

        # ── Статьи-хаб ─────────────────────────────────────────
        get_or_create_article(
            db, "Что взять с собой в Адыгею",
            excerpt="Базовый список вещей на любой сезон — и что докупить под конкретный маршрут.",
            body=(
                "Адыгея — это горы, и погода здесь меняется быстро даже летом: с утра солнце, "
                "к обеду может пойти дождь. Обязательный минимум — удобная закрытая обувь с "
                "нескользкой подошвой, ветровка или дождевик и бутылка воды.\n\n"
                "Для летних маршрутов на плато и в горы пригодятся треккинговые палки, головной "
                "убор от солнца и крем от загара — на высоте оно ощутимо сильнее.\n\n"
                "Зимой большинство высокогорных маршрутов закрыты снегом — ориентируйтесь на "
                "прогулочные места вроде Хаджохской теснины и термальных источников, туда "
                "достаточно тёплой непромокаемой обуви."
            ),
            featured_checkpoint_ids=[khadzhokh_gorge.id, thermal_tulsky.id],
        )

        get_or_create_article(
            db, "Что посмотреть в первую очередь",
            excerpt="Топ мест для первого приезда — компактно и без лишних переездов.",
            body=(
                "Если у вас один-два дня — начните с Хаджохской теснины и водопадов Руфабго, "
                "они рядом друг с другом и не требуют специальной подготовки.\n\n"
                "Если готовы к более активному дню — добавьте плато Лаго-Наки или Большую "
                "Азишскую пещеру, но учтите, что туда нужен транспорт с клиренсом.\n\n"
                "Термальные источники в Тульском — хороший вариант, чтобы закрыть день "
                "после активного маршрута."
            ),
            featured_checkpoint_ids=[khadzhokh_gorge.id, lagonaki_plateau.id],
            featured_trail_ids=[rufabgo_trail.id],
        )

        get_or_create_article(
            db, "Едем в Адыгею на 2-3 дня",
            excerpt="Короткая поездка выходного дня: Хаджох и окрестности без лишней логистики.",
            body=(
                "Маршрут для ленивых по городу: в первый день — Хаджохская теснина и "
                "водопады Руфабго, оба места рядом с Каменномостским и не требуют переездов.\n\n"
                "Маршрут для тех, кто хочет экстрима по самым ярким местам: во второй день — "
                "выезд на плато Лаго-Наки или к Большой Азишской пещере, это уже требует "
                "машины с клиренсом или трансфера.\n\n"
                "На третий день, если остаётесь до вечера — термальные источники в Тульском "
                "как спокойное завершение поездки."
            ),
            featured_trail_ids=[rufabgo_trail.id],
            featured_checkpoint_ids=[khadzhokh_gorge.id],
        )

        get_or_create_article(
            db, "Едем в Адыгею на 4-5 дней",
            excerpt="Время добавить Гузерипль и заповедник — без спешки между округами.",
            body=(
                "За 4-5 дней можно спокойно закрыть три округа: Хаджох и Даховскую в начале "
                "поездки, затем день на плато Лагонаки, и ещё день — в сторону Гузерипля, "
                "к дольмену и границе Кавказского заповедника.\n\n"
                "Для активных — это время добавить полноценный день на плато Лагонаки "
                "с многочасовым пешим выходом, а не только смотровые точки.\n\n"
                "Для тех, кто планирует маршрут поспокойнее — один день лучше оставить "
                "полностью на термальные источники и отдых без переездов."
            ),
            featured_trail_ids=[rufabgo_trail.id, lagonaki_trail.id],
        )

        get_or_create_article(
            db, "Едем в Адыгею на неделю",
            excerpt="Полная неделя: все пять округов без гонки, с днями на отдых.",
            body=(
                "Неделя позволяет пройти все пять округов не торопясь: Майкоп и термальные "
                "источники, Хаджох с тесниной и Руфабго, Даховскую, плато Лагонаки и Гузерипль "
                "с выходом к дольмену и, для подготовленных, в сторону озера Псенодах.\n\n"
                "Разумно закладывать день отдыха между активными выходами — горные маршруты "
                "утомительнее, чем кажутся по карте.\n\n"
                "Многодневные треккинги в сторону заповедника (Псенодах, Тхач) требуют "
                "заранее оформленного пропуска — планируйте это заранее, а не по приезде."
            ),
            featured_checkpoint_ids=[psenodah_lake.id],
        )

        get_or_create_article(
            db, "Адыгея с детьми",
            excerpt="Что подойдёт с малышами до 3-4-5 лет, а что стоит отложить до школьного возраста.",
            body=(
                "С детьми до 3-4-5 лет удобнее всего короткие оборудованные маршруты без "
                "резкого набора высоты: Хаджохская теснина проходится с коляской-переноской, "
                "термальные источники в Тульском — спокойный формат на полдня.\n\n"
                "Водопады Руфабго тоже подходят — тропа оборудована, но местами со ступенями, "
                "удобнее нести ребёнка на руках, чем везти коляску.\n\n"
                "Маршруты на плато Лагонаки и в пещеры лучше отложить до возраста, когда "
                "ребёнок может пройти несколько часов пешком сам — это уже не прогулочный "
                "формат."
            ),
            featured_checkpoint_ids=[khadzhokh_gorge.id, thermal_tulsky.id],
            featured_trail_ids=[rufabgo_trail.id],
        )

        get_or_create_article(
            db, "Термальные источники Адыгеи",
            excerpt="Горячие минеральные бассейны рядом с Майкопом — когда ехать и чего ожидать.",
            body=(
                "Термальные комплексы в посёлках Тульский и Цветочный работают на скважинной "
                "минеральной воде и открыты круглый год — это один из немногих форматов отдыха "
                "в Адыгее, не зависящих от погоды.\n\n"
                "Обычно это несколько бассейнов разной температуры под открытым небом — "
                "хороший вариант для завершения активного дня в горах или как отдельная "
                "спокойная поездка с детьми."
            ),
            district="maikop",
            featured_checkpoint_ids=[thermal_tulsky.id],
        )

        get_or_create_article(
            db, "Как добраться и где остановиться",
            excerpt="Логистика поездки: через какой город заезжать и как выбрать, где жить.",
            body=(
                "Ближайшие крупные точки въезда — Майкоп и Краснодар, откуда до туристических "
                "округов Адыгеи (Хаджох, Даховская) обычно час-полтора на машине.\n\n"
                "Большинство достопримечательностей компактно расположены вокруг Каменномостского "
                "и Даховской — удобно выбрать жильё в одном из этих посёлков и делать оттуда "
                "однодневные вылазки, а не переезжать каждый день.\n\n"
                "Для выездов на плато Лагонаки и к дальним точкам заповедника пригодится "
                "машина с клиренсом или трансфер — часть дорог грунтовые."
            ),
        )

        db.commit()
        print("Демо-контент готов.")


if __name__ == "__main__":
    run()
