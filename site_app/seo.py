"""SEO-настройки, которые пока живут в коде, а не в админке.

Title страницы и H1 — разные вещи: H1 остаётся живым авторским заголовком,
а в <title> добавляем формулировку, которую реально ищут («Каменномостский»,
«Адыгея», «что посмотреть»). Пусто в словаре — title собирается как раньше.
Когда правил станет больше, их стоит перенести в поле seo_title в админке.
"""
from datetime import date
from typing import Optional

# /okrugi/{slug}: title. В имени округа в базе «Округ Хаджоха» — по такому
# названию никто не ищет, ищут посёлок и «что посмотреть».
DISTRICT_TITLES = {
    "khadzhokh": "Каменномостский (Хаджох): что посмотреть самостоятельно — АдыГид",
    "guzeripl": "Гузерипль: что посмотреть, экоцентр и тропы — Адыгея | АдыГид",
    "dakhovskaya": "Даховская: что посмотреть, канатка и Гранитный каньон — Адыгея",
    "maikop": "Майкоп и окрестности: что посмотреть за день — Адыгея | АдыГид",
    "lagonaki": "Плато Лаго-Наки: что посмотреть, КПП и дорога — Адыгея | АдыГид",
}

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
    "zimoy": "Адыгея зимой: что посмотреть и что работает в 2026/27 — АдыГид",
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
        {"url": "/stati/novyy-god-v-adygee-2027", "label": "Новый год 2027", "note": "каникулы 31.12–10.01", "cover": COVERS["bison_snow"]},
        {"url": "/stati/kamennomostskiy-hadzhoh-zimoy", "label": "Хаджох зимой", "note": "часы, цены, гололёд", "cover": COVERS["rufabgo"]},
        {"url": "/stati/termalnye-istochniki-adygei", "label": "Термы", "note": "погреться после гор", "cover": COVERS["akvatermo"]},
    ],
}
_LATE_AUTUMN = dict(_WINTER, title="Поздняя осень", lead="Ноябрь — тихо и без толп, на плато уже бывает первый снег. Что работает и куда ехать.", items=[
    {"url": "/stati/adygeya-v-noyabre", "label": "Адыгея в ноябре", "note": "куда реально ехать", "cover": COVERS["rufabgo"]},
    {"url": "/stati/adygeya-v-dekabre", "label": "Адыгея в декабре", "note": "погода и что открыто", "cover": COVERS["plato_late"]},
    {"url": "/kuda/zimoy", "label": "Что открыто зимой", "note": "теснина, Руфабго, термы", "cover": COVERS["tesnina"]},
    {"url": "/stati/novyy-god-v-adygee-2027", "label": "Новый год 2027", "note": "каникулы 31.12–10.01", "cover": COVERS["bison_snow"]},
])
SEASONAL = {11: _LATE_AUTUMN, 12: _WINTER, 1: _WINTER, 2: _WINTER}


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


def place_title(name: str, district: Optional[str]) -> str:
    area = PLACE_AREA.get(district or "")
    where = f"{area}, Адыгея" if area and area not in name else "Адыгея"
    return f"{name} ({where}) — как добраться и что посмотреть"
