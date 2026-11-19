"""SEO-настройки, которые пока живут в коде, а не в админке.

Title страницы и H1 — разные вещи: H1 остаётся живым авторским заголовком,
а в <title> добавляем формулировку, которую реально ищут («Каменномостский»,
«Адыгея», «что посмотреть»). Пусто в словаре — title собирается как раньше.
Когда правил станет больше, их стоит перенести в поле seo_title в админке.
"""
from datetime import date
from typing import Optional

# /okrugi/{slug}: title. В имени округа в базе «Округ Хаджоха» — по такому
# названию никто не ищет, ищут посёлок и «что посмотреть». Формулы разные:
# одинаковый шаблон «X: что посмотреть — Адыгея» на пяти страницах Яндекс
# считает трафаретом. «Адыгея» в каждом title не обязательна — посёлки и так
# однозначные.
DISTRICT_TITLES = {
    "khadzhokh": "Каменномостский (Хаджох): что посмотреть — АдыГид",
    "guzeripl": "Гузерипль: достопримечательности и прогулки — АдыГид",
    "dakhovskaya": "Даховская: что посмотреть и куда съездить — АдыГид",
    "maikop": "Майкоп и окрестности: что посмотреть за день — АдыГид",
    "lagonaki": "Лаго-Наки: дорога, смотровые и прогулки — АдыГид",
}

# Как район называется для посетителя. В базе (и в адресах /okrugi/…) —
# «Округ Хаджоха»: внутреннее слово проекта, люди так не говорят и не ищут.
# Подпись подменяется только для имён, которые начинаются с «Округ», — если
# в админке назвать район по-человечески, возьмётся название из админки.
DISTRICT_DISPLAY = {
    "khadzhokh": "Хаджох (Каменномостский)",
    "guzeripl": "Гузерипль",
    "dakhovskaya": "Даховская",
    "maikop": "Майкоп и окрестности",
    "lagonaki": "Плато Лаго-Наки",
}


def district_display(slug: Optional[str], stored: Optional[str]) -> Optional[str]:
    if stored and not stored.strip().lower().startswith("округ"):
        return stored
    return DISTRICT_DISPLAY.get(slug or "", stored)


# /stati/{slug}: title для статей, где в заголовке нет ни «Адыгеи», ни
# топонима из запроса. H1 не меняется.
ARTICLE_TITLES = {
    "tuman-na-lago-naki-kuda-ehat": "Туман на Лаго-Наки: куда ехать вместо плато — Адыгея",
    "dve-pogody-za-odin-den-belaya-i-plato": "Погода в Адыгее: долина Белой и плато в один день",
    "posle-snegopada-kogda-razvorachivatsya": "Лаго-Наки после снегопада: когда разворачиваться",
    "yavorova-ili-lago-naki-zimoy": "Яворова поляна или Лаго-Наки зимой: что выбрать",
    "kulturnyy-den-dolmen-muzei": "Дольмены и музеи Адыгеи: культурный день без мистики",
    "gastropetlya-hadzhoh-dahovskaya": "Где поесть в Адыгее: гастропетля Хаджох — Даховская",
    "chto-posmotret-v-pervuyu-ochered": "Что посмотреть в Адыгее в первую очередь — АдыГид",
    "edem-v-adygeyu-na-2-3-dnya": "Поездка в Адыгею на 2–3 дня: маршрут и что посмотреть",
}

# /kuda/{slug}
SCENARIO_TITLES = {
    "bez-mashiny": "Адыгея без машины: что посмотреть самостоятельно на автобусе",
    "zimoy": "Адыгея зимой: что посмотреть и куда поехать — АдыГид",
}

# Какой хаб /kuda предложить в блоке «Куда дальше» под статьёй. Порядок
# важен: первое совпадение по slug статьи выигрывает.
NEXT_HUB_RULES = [
    (("s-detmi", "rebenk", "detmi"), "s-detmi"),
    (("dozhd", "tuman", "pogod"), "dozhd"),
    (("zim", "sneg", "novyy-god", "dekabr", "yanvar", "term", "lago"), "zimoy"),
    (("bez-mashiny", "krasnodar", "rostov", "moskv"), "bez-mashiny"),
]
DEFAULT_HUB = "vpervye"


def next_hub_slug(article_slug: str) -> str:
    for keys, hub in NEXT_HUB_RULES:
        if any(k in article_slug for k in keys):
            return hub
    return DEFAULT_HUB


_U = "https://hiotbrjgilwlztlfdkmg.supabase.co/storage/v1/object/public/uploads/"
# Обложки карточек сезонного блока задаются здесь: у части статей обложка
# летняя, а в зимнем блоке нужен зимний кадр. Фото — уже опубликованные на сайте.
COVERS = {
    "tesnina": _U + "448c4b816ebf4e748411e4320a874734.jpeg",
    "rufabgo": _U + "e82354484518437b90d9f59160f1924a.webp",
    "plato_late": _U + "aeb9c66353d84bb9a14e5113041d416e_thumb.webp",
    "lago_snow": _U + "698466db34694c4ea3145fbeaf81dff6_thumb.webp",
    "bison_snow": _U + "9ea554c07beb49c1ab4486b36dae0576.webp",
    "akvatermo": _U + "d92838921a9740db92fb5f597f25f17c.webp",
}

# Сезонный блок на главной. Ключ — номер месяца; карточки ссылаются на
# страницы по адресу, обложку и подпись роутер берёт из базы. Если страница
# не опубликована, карточка просто не показывается.
_WINTER = {
    "kicker": "Сейчас в Адыгее",
    "title": "Зима",
    "lead": "Снег — только наверху, в долине Белой днём около +5. Вот что реально работает и куда ехать в ближайшие недели.",
    "items": [
        {"url": "/kuda/zimoy", "label": "Что открыто зимой", "note": "теснина, Руфабго, термы, Гузерипль", "cover": COVERS["tesnina"]},
        {"url": "/stati/novyy-god-v-adygee", "label": "Новый год 2027", "note": "каникулы 31.12–10.01", "cover": COVERS["bison_snow"]},
        {"url": "/stati/kamennomostskiy-hadzhoh-zimoy", "label": "Хаджох зимой", "note": "часы, цены, гололёд", "cover": COVERS["rufabgo"]},
        {"url": "/stati/termalnye-istochniki-adygei", "label": "Термы", "note": "погреться после гор", "cover": COVERS["akvatermo"]},
    ],
}
_LATE_AUTUMN = dict(_WINTER, title="Поздняя осень", lead="Ноябрь — тихо и без толп, на плато уже бывает первый снег. Что работает и куда ехать.", items=[
    {"url": "/stati/adygeya-v-noyabre", "label": "Адыгея в ноябре", "note": "куда реально ехать", "cover": COVERS["rufabgo"]},
    {"url": "/stati/adygeya-v-dekabre", "label": "Адыгея в декабре", "note": "погода и что открыто", "cover": COVERS["lago_snow"]},
    {"url": "/kuda/zimoy", "label": "Что открыто зимой", "note": "теснина, Руфабго, термы", "cover": COVERS["tesnina"]},
    {"url": "/stati/novyy-god-v-adygee", "label": "Новый год 2027", "note": "каникулы 31.12–10.01", "cover": COVERS["bison_snow"]},
])
# Под карточками сезонного блока — строка прямых ссылок на карточки мест
# с их настоящими названиями: главная — самая сильная страница сайта, и
# с неё должны вести ссылки не только в хабы, но и в сами места.
_WINTER["places"] = [24, 40, 62, 63, 67, 55]
_LATE_AUTUMN["places"] = [24, 40, 52, 62, 67]
SEASONAL = {11: _LATE_AUTUMN, 12: _WINTER, 1: _WINTER, 2: _WINTER}


# Хаб /kuda/{slug} с ручной подборкой вместо выборки по фильтрам: зимний
# фильтр «круглый год» тянул почти весь каталог (~90 карточек) и делал хаб
# копией /mesta. Порядок — редакционный.
SCENARIO_CURATED = {
    "zimoy": {
        "places": [24, 40, 62, 63, 52, 42, 45, 25, 48, 55, 67, 68, 72, 69],
        "routes": [12, 17, 14, 13, 16, 21],
    },
}

# «С чего начать» на странице района — 3–4 главные карточки текстовыми
# ссылками с названием места (сами карточки ниже идут сеткой).
DISTRICT_START = {
    "khadzhokh": [24, 40, 42, 45],
    "guzeripl": [62, 63, 27],
    "dakhovskaya": [52, 48, 49],
    "lagonaki": [55, 25, 58, 39],
    "maikop": [67, 68, 69, 71],
}


def seasonal_for(today: Optional[date] = None) -> Optional[dict]:
    today = today or date.today()
    return SEASONAL.get(today.month)


def breadcrumbs_ld(site_url: str, crumbs: list) -> dict:
    """crumbs — [(название, путь)], главная добавляется сама."""
    items = [("АдыГид", "/")] + list(crumbs)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": site_url + path}
            for i, (name, path) in enumerate(items, start=1)
        ],
    }


# Для title карточек места: округ в базе называется «Округ Хаджоха», а ищут
# посёлок. «Хаджохская теснина (Каменномостский, Адыгея) — как добраться…»
PLACE_AREA = {
    "khadzhokh": "Каменномостский",
    "guzeripl": "Гузерипль",
    "dakhovskaya": "Даховская",
    "lagonaki": "Лаго-Наки",
    "maikop": "Майкоп",
}


# Title ключевых карточек — под то, что про место реально спрашивают
# (билеты, дорога, зимой, с детьми), и с разными формулами. Остальные карточки
# собираются по общему правилу ниже. Цены и часы в title не пишем: их нет
# в подтверждённом виде.
PLACE_TITLES = {
    24: "Хаджохская теснина: билеты, дорога и прогулка — АдыГид",
    40: "Водопады Руфабго: как добраться и что учесть — АдыГид",
    52: "Гранитный каньон: смотровые и как добраться — АдыГид",
    55: "Плато Лаго-Наки: КПП, дорога и что посмотреть — АдыГид",
    62: "Музей природы в Гузерипле: что внутри и как совместить — АдыГид",
    63: "Вольерный комплекс в Гузерипле: животные заповедника — АдыГид",
    25: "Большая Азишская пещера: экскурсия, ступени и дорога — АдыГид",
    48: "Савранская канатная дорога в Даховской: что проверить — АдыГид",
    42: "Казачий камень по дороге в Даховскую: как посмотреть — АдыГид",
    67: "«АкваТермо» в Тульском: термальные бассейны под Майкопом — АдыГид",
    68: "«Кедровый бор» в Цветочном: термальный бассейн — АдыГид",
    72: "Термы Псыгупс под Майкопом: что проверить до поездки — АдыГид",
    30: "Михайло-Афонская пустынь: подземный монастырь и Физиабго — АдыГид",
    45: "Музей «Беловодье» в Хаджохе: аммониты и быт — АдыГид",
}


def place_title(name: str, district: Optional[str], place_id: Optional[int] = None) -> str:
    # Карточки с проверенными часами/ценой — под запросы «время работы»,
    # «цена входа» (fact_title ниже); остальные — по прежним правилам.
    by_facts = fact_title(place_id, name)
    if by_facts:
        return by_facts
    if place_id in PLACE_TITLES:
        return PLACE_TITLES[place_id]
    area = PLACE_AREA.get(district or "")
    where = f"{area}, Адыгея" if area and area not in name else "Адыгея"
    return f"{name} ({where}) — как добраться и что посмотреть"


# ───────────────── «Коротко для поездки» на карточке места ─────────────────
# Практические поля приоритетных карточек. Это то, что люди ищут перед
# выездом («… время работы», «… цена входа»), поэтому блок стоит сразу под
# H1, рендерится таблицей (Яндекс берёт такие таблицы в быстрые ответы),
# а проверенные факты дублируются в JSON-LD и в title/description.
#
# Правила текста:
# - в поле — только сам факт, без оговорок; источник и дата проверки
#   пишутся один раз под таблицей (FACT_SOURCES + "checked");
# - чего нет в подтверждённом виде, так и пишем (NO_PRICE / NO_HOURS) или
#   помечаем «по путеводителям» — но не выдаём за официальный факт;
# - "facts" заполняется ТОЛЬКО из официального источника. По нему строятся
#   JSON-LD (часы, цена, наличные, животные) и SEO-title — в разметку и
#   сниппет не попадает ничего непроверенного.
#
# Время посещения, если тут не задано, берётся из duration_minutes карточки,
# «С чем совместить» — ссылками на карточки. Пустое поле не показывается.
PRACTICAL_LABELS = [
    ("hours", "Часы работы"),
    ("tickets", "Вход"),
    ("cash", "Оплата"),
    ("how", "Как добраться"),
    ("visit", "Время посещения"),
    ("winter", "Зимой"),
    ("kids", "С детьми"),
    ("pets", "С животными"),
    ("combine", "С чем совместить"),
]
# Служебные ключи записи PLACE_PRACTICAL (не строки таблицы).
PRACTICAL_META_KEYS = {"route", "facts", "checked", "sources"}

NO_PRICE = "Официального прайса нет — уточни у объекта перед поездкой."
NO_HOURS = "Официальных часов нет — проверь перед выездом, особенно вне летнего сезона."

FACT_SOURCES = {
    "zapoved_kpp": {"title": "Кавказский заповедник: пункты выдачи пропусков",
                    "url": "https://www.kavkazzapoved.ru/punkty-vydachi-propuskov"},
    "zapoved_hours": {"title": "Кавказский заповедник: режим работы",
                      "url": "https://www.kavkazzapoved.ru/rezhim-raboty"},
    "zapoved_order": {"title": "приказ заповедника № 359 от 14.08.2026",
                      "url": "https://www.kavkazzapoved.ru/sites/default/files/fields/2026/100934_0.pdf"},
    "zapoved_news": {"title": "новость заповедника о плате с 15.08.2026",
                     "url": "https://www.kavkazzapoved.ru/news/s-15-avgusta-v-kavkazskom-zapovednike-menyaetsya-stoimost-posescheniya-rekreacionnykh-obektov"},
    "zapoved_rules": {"title": "правила посещения заповедника",
                      "url": "https://www.kavkazzapoved.ru/pravila"},
    "zapoved_30g": {"title": "маршрут № 30 Г на сайте заповедника",
                    "url": "https://www.kavkazzapoved.ru/routes/no30-g-kpp-uzurub-priyut-fisht-kpp-ruchey-belyy"},
    "gov_tesnina": {"title": "туристический портал Правительства Адыгеи",
                    "url": "https://pokolenie.adygheya.gov.ru/tourism/khadzhokhskaya-tesnina/"},
    "gov_savran": {"title": "туристический портал Правительства Адыгеи",
                   "url": "https://pokolenie.adygheya.gov.ru/tourism/savranskaya-kanatnaya-doroga/"},
    "gov_meshoko": {"title": "туристический портал Правительства Адыгеи",
                    "url": "https://pokolenie.adygheya.gov.ru/tourism/ekstrim-park-meshoko/"},
    "gov_azish": {"title": "туристический портал Правительства Адыгеи",
                  "url": "https://pokolenie.adygheya.gov.ru/tourism/bolshaya-azishskaya-peshchera/"},
    "gov_natsmuzey": {"title": "туристический портал Правительства Адыгеи",
                      "url": "https://pokolenie.adygheya.gov.ru/tourism/natsionalnyy-muzey-respubliki-adygeya/"},
    "gov_vostok": {"title": "туристический портал Правительства Адыгеи",
                   "url": "https://pokolenie.adygheya.gov.ru/tourism/severokavkazskiy-filial-gosudarstvennogo-muzeya-iskusstva-narodov-vostoka/"},
    "aquatermo": {"title": "официальный сайт «АкваТермо»",
                  "url": "https://aquatermo01.ru/residence/day/"},
}

# Плата заповедника: приказ № 359 — 500 ₽ за посещение ООПТ; экоцентр
# «Гузерипль» отдельно назван в новости от 14.08.2026. Льготы — приложение
# к приказу (21 категория), оформляются только в кассе по документам.
ZAPOVED_PRICE = 500
ZAPOVED_FREE = ("Бесплатно — дети и школьники, пенсионеры, многодетные родители, "
                "люди с инвалидностью и ещё ряд категорий, по документам в кассе.")
_KPP_LAGO = {
    "hours": "касса КПП «Лагонаки» ежедневно 05:00–20:00",
    "opens": "05:00", "closes": "20:00", "hours_place": "Касса КПП «Лагонаки»",
    "price": ZAPOVED_PRICE, "price_label": "500 ₽ за посещение заповедника, дети и пенсионеры бесплатно",
    "price_place": "Посещение Кавказского заповедника через КПП «Лагонаки»",
    "cash_only": True, "pets": False,
    "locality": "КПП «Лагонаки», дорога Р254 от Даховской",
}

PLACE_PRACTICAL = {
    24: {
        "facts": {"name": "Хаджохская теснина", "hours": "ежедневно 08:00–18:00",
                  "opens": "08:00", "closes": "18:00",
                  "locality": "пос. Каменномостский", "phone": "+7 918 222-40-97"},
        "checked": "2026-11-19", "sources": ["gov_tesnina"],
        "hours": "Ежедневно 08:00–18:00, в темноте включают подсветку. Справки: +7 918 222-40-97.",
        "tickets": "Платно. Официального прайса нет; по данным путеводителей — около 700 ₽ со взрослого.",
        "how": "Прямо в посёлке Каменномостский (Хаджох), подъезд по асфальту — удобно заглянуть до или после заселения.",
        "visit": "Оборудованный маршрут около 800 м, сама теснина — около 400 м. Час-полтора без спешки.",
        "winter": "Открыта круглый год, но на ступенях и настилах бывает наледь — нужна обувь с протектором.",
        "kids": "Да, но держись подальше от края. Для коляски маршрут не подходит: есть ступени.",
        "combine": [40, 42], "route": 12,
    },
    40: {
        "visit": "Около 2,5 часа на первые водопады с остановками; дальняя часть ущелья — дольше и заметно сложнее.",
        "how": "Обычно заходят с оборудованного входа у моста через Белую рядом с Каменномостским. Обходная тропа со стороны посёлка круче.",
        "tickets": "Платно. Официального прайса нет; по данным путеводителей — около 600 ₽ со взрослого.",
        "hours": "Официальных часов нет. По путеводителям касса вне лета работает до 17:00–18:00 — приходи до обеда.",
        "winter": "Тропа круглогодичная, но мокрые камни, мостики и лестницы зимой скользкие. После осадков ручей полноводнее и опаснее.",
        "kids": "Первые водопады по оборудованной части — да; дальше лестницы и мокрые камни, их лучше оставить.",
        "combine": [24, 42], "route": 12,
    },
    62: {
        "facts": {"name": "Музей природы в Гузерипле", "hours": "ежедневно 10:00–17:00",
                  "opens": "10:00", "closes": "17:00", "hours_place": "Экоцентр «Гузерипль»",
                  "price": ZAPOVED_PRICE, "price_label": "500 ₽, дети и пенсионеры бесплатно",
                  "price_place": "Посещение экоцентра «Гузерипль»",
                  "locality": "пос. Гузерипль", "street": "ул. Заречная, 5", "phone": "+7 918 424-13-48"},
        "checked": "2026-11-19", "sources": ["zapoved_hours", "zapoved_news", "zapoved_rules"],
        "hours": "Ежедневно 10:00–17:00 (экоцентр «Гузерипль», ул. Заречная, 5). Тел. +7 918 424-13-48.",
        "tickets": "500 ₽ с человека за посещение экоцентра в день, с 15.08.2026. " + ZAPOVED_FREE,
        "pets": "По правилам заповедника — без домашних животных.",
        "how": "В посёлке Гузерипль, рядом с вольерами и дольменом; по дороге вдоль Белой — остановка у Гранитного каньона.",
        "winter": "Хороший план на холодный или дождливый день. После снегопада проверь дорогу на Гузерипль.",
        "kids": "Да: экспозиции с животными заповедника и рельефная карта.",
        "combine": [63, 27, 52], "route": 17,
    },
    63: {
        "facts": {"name": "Вольерный комплекс в Гузерипле", "hours": "ежедневно 10:00–17:00",
                  "opens": "10:00", "closes": "17:00", "hours_place": "Экоцентр «Гузерипль»",
                  "price": ZAPOVED_PRICE, "price_label": "500 ₽, дети и пенсионеры бесплатно",
                  "price_place": "Посещение экоцентра «Гузерипль»",
                  "locality": "пос. Гузерипль", "street": "ул. Заречная, 5", "phone": "+7 918 424-13-48"},
        "checked": "2026-11-19", "sources": ["zapoved_hours", "zapoved_news", "zapoved_rules"],
        "hours": "Ежедневно 10:00–17:00 — режим экоцентра «Гузерипль». Тел. +7 918 424-13-48.",
        "tickets": "500 ₽ с человека за посещение экоцентра в день, с 15.08.2026. " + ZAPOVED_FREE,
        "pets": "По правилам заповедника — без домашних животных.",
        "how": "Гузерипль, рядом с музеем природы и дольменом.",
        "winter": "Место круглогодичное, но прогулка под открытым небом — оденься теплее.",
        "kids": "Да. Встречу с конкретным животным никто не гарантирует — состав обитателей меняется.",
        "combine": [62, 27], "route": 17,
    },
    52: {
        "how": "Долина Белой между Даховской и Гузериплем, подъезд по асфальту. Смотри с безопасной обзорной точки у дороги.",
        "winter": "Доступен круглый год, если дорога на Гузерипль в порядке. В гололёд к краю не подходи.",
        "kids": "Да, со смотровой. Ограждения есть не везде — держи детей за руку.",
        "combine": [62, 63], "route": 14,
    },
    55: {
        "facts": dict(_KPP_LAGO, name="Плато Лаго-Наки"),
        "checked": "2026-11-19", "sources": ["zapoved_kpp", "zapoved_order", "zapoved_rules"],
        "hours": "Касса КПП «Лагонаки» — ежедневно 05:00–20:00. Дорога и смотровые до шлагбаума открыты без пропуска.",
        "tickets": "500 ₽ с человека за посещение заповедника за шлагбаумом КПП (с 15.08.2026). " + ZAPOVED_FREE,
        "cash": "Только наличные — карту на КПП не принимают.",
        "pets": "За КПП — без домашних животных: это территория заповедника.",
        "visit": "Полдня и больше: только дорога от Даховской до КПП — серпантин.",
        "how": "Со стороны Даховской по серпантину до КПП «Лагонаки», асфальт до шлагбаума. Перед выездом проверь дорожные ограничения.",
        "winter": "Наверху снег, когда внизу его нет. Нужны зимние шины, после снегопада движение могут ограничить.",
        "kids": "Смотровые у дороги — да; походы за КПП — по силам и только по разрешённым маршрутам.",
        "combine": [58, 39, 25], "route": 16,
    },
    56: {
        "facts": dict(_KPP_LAGO, name="Каменное море на Лаго-Наки"),
        "checked": "2026-11-19", "sources": ["zapoved_kpp", "zapoved_order", "zapoved_rules"],
        "hours": "Вход через кассу КПП «Лагонаки» — ежедневно 05:00–20:00. Успей вернуться к закрытию.",
        "tickets": "500 ₽ с человека за посещение заповедника (с 15.08.2026). " + ZAPOVED_FREE,
        "cash": "Только наличные — карту на КПП не принимают.",
        "pets": "Без домашних животных: это территория заповедника.",
        "how": "Сначала до КПП «Лагонаки» по серпантину от Даховской, дальше — только по разрешённому маршруту заповедника.",
        "winter": "Зимой выход зависит от того, открыт ли маршрут и проезд к КПП. Не планируй его как зимнюю прогулку по умолчанию.",
        "kids": "Только если маршрут открыт и по силам: это уже заповедник, не смотровая у дороги.",
        "combine": [55, 25],
    },
    64: {
        "facts": {"name": "Яворова поляна", "hours": "касса КПП «Узуруб» ежедневно 06:00–20:00",
                  "opens": "06:00", "closes": "20:00", "hours_place": "Касса КПП «Узуруб»",
                  "price": ZAPOVED_PRICE, "price_label": "500 ₽ за посещение заповедника за КПП, дети и пенсионеры бесплатно",
                  "price_place": "Посещение Кавказского заповедника через КПП «Узуруб»",
                  "cash_only": True, "locality": "пос. Гузерипль"},
        "checked": "2026-11-19", "sources": ["zapoved_kpp", "zapoved_30g", "zapoved_order", "zapoved_news", "zapoved_rules"],
        "hours": "Касса КПП «Узуруб» за поляной — ежедневно 06:00–20:00.",
        "tickets": ("Сама поляна — без билета. Дальше, за КПП «Узуруб», — 500 ₽ с человека за посещение заповедника; "
                    "на многодневных маршрутах — 500 ₽ за первый день и 300 ₽ за каждый следующий. " + ZAPOVED_FREE),
        "cash": "На КПП «Узуруб» — только наличные.",
        "pets": "За КПП — без домашних животных: это территория заповедника.",
        "how": "От Гузерипля по маршруту № 30 Г — на машине или пешком. КПП «Узуруб» — в 20 км от посёлка, недалеко за поляной.",
        "winter": "Маршрут № 30 Г обычно открыт с июня по сентябрь, точные даты — приказами заповедника. Зимой дорогу к поляне уточняй заранее.",
        "kids": "Поляна как смотровая и пикник — по силам; выход за КПП — только если маршрут открыт и по силам.",
        "combine": [65, 62, 55],
    },
    48: {
        "facts": {"name": "Савранская канатная дорога",
                  "hours": "ежедневно 9:00–17:00, летом 10:00–17:30",
                  "locality": "ст. Даховская", "phone": "+7 928 669-65-29"},
        "checked": "2026-11-19", "sources": ["gov_savran"],
        "hours": "Ежедневно 9:00–17:00, летом 10:00–17:30. Бывают профилактические дни, а ветер и снег останавливают подъём — позвони: +7 928 669-65-29.",
        "tickets": NO_PRICE,
        "visit": "Около 1,5 км, подъём около 20 минут, верхняя станция — почти 1000 м над уровнем моря.",
        "how": "Нижняя станция в районе Даховской, подъезд по асфальту.",
        "winter": "Подъём возможен, но по обледеневшему хребту наверху не ходи только потому, что удалось подняться.",
        "kids": "Подъём и смотровые у верхней станции — да; прогулка по хребту — по силам и погоде.",
        "combine": [42, 49], "route": 13,
    },
    67: {
        "facts": {"name": "«АкваТермо» в Тульском", "hours": "ежедневно 09:00–23:00, последний заход в 21:00",
                  "opens": "09:00", "closes": "23:00",
                  "price": 1150, "price_label": "от 1 150 ₽ за 2 часа",
                  "price_place": "Дневное посещение, взрослый, 2 часа (обычный тариф 2026)",
                  "pets": False, "locality": "пос. Тульский", "street": "ул. Железнодорожная, 55",
                  "phone": "+7 918 920-87-77"},
        "checked": "2026-11-19", "sources": ["aquatermo"],
        "hours": "Ежедневно 09:00–23:00, последний заход в источник — в 21:00.",
        "tickets": ("Обычный тариф 2026: 2 часа — 1 150 ₽, 3 часа — 1 600 ₽ со взрослого; дети 3–12 лет — 575 и 800 ₽, до 3 лет бесплатно. "
                    "31.12.2026–08.01.2027 — праздничный прайс: 1 500 и 1 850 ₽. С 9 января 2027: 2 часа (+1 в подарок) — 1 200 ₽, 3 часа (+1) — 1 680 ₽."),
        "pets": "С животными нельзя — так в правилах комплекса.",
        "how": "Посёлок Тульский, ул. Железнодорожная, 55. Схему подъезда сверь у комплекса, не по случайной точке навигатора.",
        "winter": "Вода 36–38 °C, пар над бассейнами — главный вечерний пункт после гор.",
        "kids": "Нужен документ на каждого ребёнка; если везут бабушка или дедушка — нотариальная доверенность от родителей.",
        "combine": [72, 68, 38],
    },
    68: {
        "how": "Посёлок Цветочный, улица Школьная, 16А.",
        "tickets": NO_PRICE,
        "hours": "По словам комплекса: пн 12:00–21:30, вт–вс 9:00–21:30, вход до 20:00. В праздники может меняться.",
        "winter": "Зимой вода 36–38 °C, летом 30–32 °C (по данным комплекса).",
        "kids": "Отдельного детского бассейна нет — важно знать заранее.",
        "combine": [80, 67], "route": 21,
    },
    72: {
        "how": "У посёлков Тульский и Удобный под Майкопом, на машине. В выходные проверь, есть ли места на парковке.",
        "tickets": NO_PRICE,
        "hours": NO_HOURS,
        "winter": "Тёплый вариант на межсезонье и зиму без выезда в высокогорье.",
        "kids": "Проверь, какие бассейны работают и какие есть ограничения для детей.",
        "combine": [67, 38],
    },
    25: {
        "facts": {"name": "Большая Азишская пещера",
                  "hours": "осень–весна 9:00–18:00, летом 8:30–19:00, экскурсии каждые полчаса",
                  "locality": "Азишский перевал", "phone": "+7 918 088-34-98"},
        "checked": "2026-11-19", "sources": ["gov_azish"],
        "hours": "Осень–весна: 9:00–18:00, последний заход в 17:30. Лето: 8:30–19:00, последний заход в 18:30. Экскурсии каждые полчаса. Тел. +7 918 088-34-98.",
        "tickets": "Только с экскурсией. " + NO_PRICE,
        "how": "По дороге со стороны Даховской через район Азишского перевала. Административно это уже Краснодарский край.",
        "winter": "Внутри погода не мешает, но горная дорога к пещере зимой может быть сложной.",
        "kids": "Коляска не пройдёт — подземная лестница. Маленьких на руках по скользким ступеням не неси.",
        "combine": [57, 39], "route": 16,
    },
    42: {
        "how": "Валун у дороги между Каменномостским и Даховской. Сначала найди место, где можно безопасно припарковаться.",
        "winter": "Посмотреть с безопасного места проще, чем ехать наверх, но учитывай гололёд и узкие обочины.",
        "kids": "Да, но ради кадра не выходи на проезжую часть.",
        "combine": [24, 48],
    },
    45: {
        "how": "В Каменномостском, у выезда в сторону теснины; асфальт и парковка у входа.",
        "tickets": NO_PRICE,
        "hours": "Частный музей — уточни, открыт ли он в день поездки.",
        "winter": "Вариант на день непогоды, если музей открыт.",
        "kids": "Да, особенно после Долины аммонитов: видно, что у «камня с завитком» внутри.",
        "combine": [41, 24],
    },
    57: {
        "how": "Смотровая у дороги на плато, через Азишский перевал со стороны Даховской.",
        "tickets": "Бесплатно: точка у дороги, до шлагбаума КПП. Пропуск нужен, только если идёшь на территорию заповедника.",
        "winter": "Горная дорога: зимние шины, после снегопада возможны ограничения.",
        "kids": "Да, если смотришь с безопасного места у дороги и не выходишь на проезжую часть.",
        "combine": [55, 25, 39],
    },
    43: {
        "facts": {"name": "Экстрим-парк «Мишоко»", "hours": "ежедневно 10:00–17:00",
                  "opens": "10:00", "closes": "17:00", "locality": "пос. Каменномостский"},
        "checked": "2026-11-19", "sources": ["gov_meshoko"],
        "hours": "Ежедневно 10:00–17:00.",
        "tickets": NO_PRICE,
        "how": "Из Каменномостского по ул. Мира до указателя «Экстрим-парк «Мишоко»», через железнодорожные пути и дальше по указателям.",
        "winter": "Часть аттракционов зависит от погоды — уточни, что работает в день поездки.",
        "kids": "Есть детский скалодром; возраст и допуск к аттракционам решают инструкторы.",
        "combine": [24, 40],
    },
    69: {
        "facts": {"name": "Национальный музей Адыгеи в Майкопе", "hours": "вт–вс 11:00–20:00, пн выходной",
                  "opens": "11:00", "closes": "20:00",
                  "days": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                  "locality": "Майкоп", "street": "ул. Советская, 229", "phone": "+7 988 477-24-88"},
        "checked": "2026-11-19", "sources": ["gov_natsmuzey"],
        "hours": "Вторник–воскресенье 11:00–20:00, понедельник — выходной. Справки: +7 988 477-24-88.",
        "tickets": NO_PRICE,
        "how": "Майкоп, ул. Советская, 229 — центр города.",
        "kids": "Да, музей рекомендуют для семейного визита.",
        "combine": [76, 77, 71],
    },
    76: {
        "facts": {"name": "Музей Востока в Майкопе", "hours": "вт–пт 10:30–19:30, сб–вс 10:00–18:00, пн выходной",
                  "hours_spec": [
                      {"days": ["Tuesday", "Wednesday", "Thursday", "Friday"], "opens": "10:30", "closes": "19:30"},
                      {"days": ["Saturday", "Sunday"], "opens": "10:00", "closes": "18:00"},
                  ],
                  "locality": "Майкоп", "phone": "+7 8772 52-79-53"},
        "checked": "2026-11-19", "sources": ["gov_vostok"],
        "hours": "Вторник–пятница 10:30–19:30, суббота и воскресенье 10:00–18:00, понедельник — выходной. Тел. +7 8772 52-79-53.",
        "tickets": NO_PRICE,
        "kids": "Да, музей рекомендуют для семейного визита.",
        "combine": [69, 77, 71],
    },
}

_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]


def place_facts(place_id: Optional[int]) -> Optional[dict]:
    """Проверенные факты карточки (только из официального источника) или None."""
    cfg = PLACE_PRACTICAL.get(place_id or -1) or {}
    return cfg.get("facts")


def practical_checked(place_id: Optional[int]) -> Optional[dict]:
    """Строка «Проверено … · источники» под таблицей: одна на карточку."""
    cfg = PLACE_PRACTICAL.get(place_id or -1) or {}
    iso = cfg.get("checked")
    if not iso:
        return None
    d = date.fromisoformat(iso)
    seen, sources = set(), []
    for key in cfg.get("sources", []):
        src = FACT_SOURCES[key]
        if src["url"] in seen:
            continue
        seen.add(src["url"])
        sources.append(src)
    return {"iso": iso, "label": f"{d.day} {_MONTHS[d.month - 1]} {d.year}",
            "short": d.strftime("%d.%m.%Y"), "sources": sources}


def practical_heading(place_id: Optional[int], name: str) -> str:
    """Заголовок блока — естественной фразой запроса, если есть факты."""
    f = place_facts(place_id)
    if not f:
        return "Коротко для поездки"
    n = f.get("name") or name
    if f.get("price") is not None:
        return f"{n}: время работы и цена входа"
    return f"{n}: время работы и как добраться"


def fact_title(place_id: Optional[int], name: str) -> Optional[str]:
    """SEO-title для карточек с проверенными фактами: под запросы
    «… время работы», «… цена входа 2026». Цифр в title нет: они живут в
    description и в самом блоке, где у них есть дата проверки."""
    f = place_facts(place_id)
    if not f or not f.get("hours"):
        return None
    n = f.get("name") or name
    if f.get("price") is not None:
        return f"{n}: время работы, цена входа 2026, как добраться"
    return f"{n}: время работы 2026 и как добраться"


def fact_description(place_id: Optional[int], name: str) -> Optional[str]:
    """Meta description из реальных полей: часы, вход, оплата, дата проверки."""
    f = place_facts(place_id)
    chk = practical_checked(place_id)
    if not f or not chk:
        return None
    n = f.get("name") or name
    parts = []
    if f.get("hours"):
        h = f["hours"]
        parts.append(f"{n}: {h[0].lower() + h[1:]}.")
    if f.get("price_label"):
        pay = ", только наличные" if f.get("cash_only") else ""
        parts.append(f"Вход — {f['price_label']}{pay}.")
    elif f.get("cash_only"):
        parts.append("Оплата только наличными.")
    if f.get("phone") and not f.get("price_label"):
        parts.append(f"Справки: {f['phone']}.")
    parts.append(f"Проверено {chk['short']}.")
    tail = "Как добраться, что учесть зимой и с детьми."
    if len(" ".join(parts)) + len(tail) < 175:
        parts.append(tail)
    return " ".join(parts)


def _hours_spec(f: dict) -> list:
    rows = f.get("hours_spec")
    if not rows and f.get("opens") and f.get("closes"):
        rows = [{"days": f.get("days") or _WEEK, "opens": f["opens"], "closes": f["closes"]}]
    out = []
    for r in rows or []:
        spec = {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["https://schema.org/" + d for d in r["days"]],
            "opens": r["opens"], "closes": r["closes"],
        }
        if f.get("hours_place"):
            spec["description"] = f["hours_place"]
        out.append(spec)
    return out


def place_ld(place_id: int, *, name: str, url: str, description: str, images: list,
             lat: Optional[float], lon: Optional[float],
             is_paid: Optional[bool] = None) -> list:
    """JSON-LD карточки места: TouristAttraction и, если цена проверена,
    отдельный Offer (у Place/TouristAttraction в schema.org нет offers и
    petsAllowed, поэтому цена — Offer с availableAtOrFrom, а наличные и
    животные — amenityFeature). Без проверенных фактов — прежняя разметка."""
    f = place_facts(place_id) or {}
    chk = practical_checked(place_id) if f else None
    place_ref = url + "#place"
    address = {"@type": "PostalAddress", "addressRegion": "Республика Адыгея", "addressCountry": "RU"}
    if f.get("locality"):
        address["addressLocality"] = f["locality"]
    if f.get("street"):
        address["streetAddress"] = f["street"]
    ld = {
        "@context": "https://schema.org",
        "@type": "TouristAttraction",
        "@id": place_ref,
        "name": name,
        "description": description,
        "url": url,
        "image": images,
        "address": address,
    }
    if lat is not None and lon is not None:
        ld["geo"] = {"@type": "GeoCoordinates", "latitude": round(lat, 6), "longitude": round(lon, 6)}
    # isAccessibleForFree пишем только когда стоимость известна: false при
    # неизвестной цене поисковик читает как «вход платный».
    if f.get("price") is not None:
        ld["isAccessibleForFree"] = f["price"] == 0
    elif is_paid is not None:
        ld["isAccessibleForFree"] = not is_paid
    if f:
        ld["publicAccess"] = True
        spec = _hours_spec(f)
        if spec:
            ld["openingHoursSpecification"] = spec
        if f.get("phone"):
            ld["telephone"] = f["phone"]
        features = []
        if f.get("cash_only"):
            features.append({"@type": "LocationFeatureSpecification", "name": "Оплата только наличными", "value": True})
        if f.get("pets") is not None:
            features.append({"@type": "LocationFeatureSpecification", "name": "Можно с домашними животными", "value": bool(f["pets"])})
        if features:
            ld["amenityFeature"] = features
    if chk:
        ld["mainEntityOfPage"] = {"@type": "WebPage", "@id": url, "dateModified": chk["iso"]}
    out = [ld]
    if f.get("price") is not None and chk:
        offer = {
            "@context": "https://schema.org",
            "@type": "Offer",
            "name": f.get("price_place") or f"Посещение: {name}",
            "description": f.get("price_label"),
            "price": f["price"],
            "priceCurrency": "RUB",
            "availableAtOrFrom": {"@id": place_ref},
            "url": chk["sources"][0]["url"] if chk["sources"] else url,
        }
        if f.get("cash_only"):
            offer["acceptedPaymentMethod"] = "https://schema.org/Cash"
        out.append(offer)
    return out
