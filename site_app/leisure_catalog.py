"""Справочник досуга и расчёт сервисного сбора.

Сбор гостя за досуг — 5%. Процент жилья (partners.service_fee_pct) здесь не читается
и не пишется. Как считать и показывать сбор, задаёт одна строка LEISURE_FEE_SCHEME.
Пока владелец не выбрал схему, стоит from_price: 5% вычитаются из указанной цены,
а сумма на публичной карточке не пишется.
"""
from decimal import Decimal

LEISURE_SERVICE_FEE_PCT = Decimal("5")
# Одна настройка сбора досуга. Меняется в этом файле.
#   from_price         — 5% из указанной цены, на карточке сумму не показываем (сейчас)
#   from_price_public  — то же, сумму на карточке показываем
#   on_top             — 5% сверху к цене, сумму не показываем
#   on_top_public      — 5% сверху, сумму показываем
#   hidden             — для гостя сбор не считаем и не показываем
LEISURE_FEE_SCHEME = "from_price"
_FEE_SCHEMES = {
    "from_price": {"deduct": True, "public": False},
    "from_price_public": {"deduct": True, "public": True},
    "on_top": {"deduct": False, "public": False},
    "on_top_public": {"deduct": False, "public": True},
    "hidden": {"deduct": False, "public": False, "skip": True},
}
CONSENT_VERSION = "1.1"

# code, подпись, нужно ли отдельное поле «состояние» (прокат, техника, суда)
ACTIVITIES = [
    ("excursion", "Экскурсия", False),
    ("horse", "Конная прогулка", False),
    ("hike", "Поход с гидом", False),
    ("masterclass", "Мастер-класс", False),
    ("rafting", "Рафтинг и сплав", True),
    ("jeeping", "Джиппинг", True),
    ("quad", "Квадроциклы и багги", True),
    ("rental", "Прокат снаряжения", True),
    ("cable", "Канатная дорога", False),
    ("other", "Другое", False),
]
ACTIVITY_BY_CODE = {code: (title, needs_state) for code, title, needs_state in ACTIVITIES}
STATE_REQUIRED = {code for code, _title, needs in ACTIVITIES if needs}

LEGAL_STATUSES = [
    ("self_employed", "Самозанятый"),
    ("ip", "ИП"),
    ("company", "ООО или другая организация"),
    ("individual", "Физлицо без статуса"),
]
LEGAL_BY_CODE = dict(LEGAL_STATUSES)

SEASONS = [
    ("all_year", "Круглый год"),
    ("spring", "Весна"),
    ("summer", "Лето"),
    ("autumn", "Осень"),
    ("winter", "Зима"),
]
SEASON_BY_CODE = dict(SEASONS)

DIFFICULTIES = [
    ("easy", "Лёгкий"),
    ("medium", "Средний"),
    ("hard", "Сложный"),
    ("none", "Не про сложность"),
]
DIFFICULTY_BY_CODE = dict(DIFFICULTIES)

TRANSFERS = [
    ("none", "Трансфера нет"),
    ("optional", "Трансфер можно заказать отдельно"),
    ("included", "Трансфер входит в цену"),
]
TRANSFER_BY_CODE = dict(TRANSFERS)

LANGUAGES = [
    ("ru", "Русский"),
    ("ady", "Адыгейский"),
    ("en", "Английский"),
]
LANGUAGE_BY_CODE = dict(LANGUAGES)

PRICE_UNITS = [
    ("person", "с человека"),
    ("group", "за группу"),
    ("hour", "за час"),
    ("day", "за день"),
    ("item", "за единицу"),
]
PRICE_UNIT_BY_CODE = dict(PRICE_UNITS)

GEAR_ANSWER = [("yes", "Да"), ("no", "Нет"), ("na", "Не выдаём")]
BRIEFING_ANSWER = [("yes", "Да, проводим"), ("no", "Нет")]
WATER_TYPES = {"rafting"}

# Поля только у части типов. public=False — номер документа: админка видит, сайт нет.
CATEGORY_FIELDS = {
    "rafting": [
        {"key": "flood_cancel", "label": "Отмена при паводке", "hint": "При каком уровне воды или дожде выход не состоится", "required": True, "public": True},
        {"key": "vest_for_all", "label": "Жилеты на сплаве", "hint": "Кому выдаёте и есть ли детские", "required": True, "public": True},
        {"key": "water_briefing", "label": "Инструктаж перед водой", "hint": "Кто проводит и что в нём", "required": True, "public": True},
    ],
    "horse": [
        {"key": "age", "label": "Возраст для конной прогулки", "hint": "С какого возраста сажаете и с кем ребёнок", "required": True, "public": True},
        {"key": "weight", "label": "Ограничение по весу всадника", "hint": "Например: до 100 кг", "required": True, "public": True},
    ],
    "jeeping": [
        {"key": "driving_license", "label": "Какие права нужны гостю", "hint": "Если за рулём только водитель организатора — так и напишите", "required": True, "public": True},
        {"key": "passenger_license", "label": "Лицензия на перевозку пассажиров", "hint": "Номер и срок. На сайте номер не показываем", "required": True, "public": False},
    ],
    "quad": [
        {"key": "driving_license", "label": "Какие права нужны гостю", "hint": "Категория или «права не нужны, ведёт инструктор»", "required": True, "public": True},
        {"key": "passenger_license", "label": "Лицензия на перевозку пассажиров", "hint": "Номер и срок. На сайте номер не показываем", "required": True, "public": False},
    ],
    "hike": [
        {"key": "permit_needed", "label": "Нужен пропуск в заповедник", "hint": "", "required": True, "public": True, "choices": [("yes", "Да"), ("no", "Нет")]},
        {"key": "permit_note", "label": "Что сделать гостю, если пропуск нужен", "hint": "Без номера пропуска и других документов", "required": False, "public": True, "required_if": ("permit_needed", "yes")},
    ],
    "cable": [
        {"key": "cable_rules", "label": "Рост, возраст и как едут", "hint": "Ограничения самой дороги", "required": True, "public": True},
        {"key": "cable_weather", "label": "Когда дорога не работает", "hint": "Ветер, гроза, техобслуживание", "required": True, "public": True},
    ],
}


def category_fields(activity: str | None) -> list[dict]:
    return CATEGORY_FIELDS.get(activity or "", [])


def public_extra(activity: str | None, extra: dict | None) -> list[tuple[str, str]]:
    rows = []
    data = extra or {}
    for field in category_fields(activity):
        if not field.get("public", True):
            continue
        value = data.get(field["key"])
        if not value:
            continue
        if field.get("choices"):
            value = dict(field["choices"]).get(value, value)
        rows.append((field["label"], value))
    return rows


STATUSES = [
    ("pending", "На модерации"),
    ("approved", "Опубликовано"),
    ("rejected", "Отклонено"),
]
STATUS_BY_CODE = dict(STATUSES)


def fee_parts(price, pct=None, scheme: str | None = None) -> dict | None:
    """Сбор по LEISURE_FEE_SCHEME. None, если цены числом нет.

    discount заполняется только для схемы «из цены» и нужен внутреннему расчёту.
    На публичной карточке это слово не выводится.
    """
    if price is None or price == "":
        return None
    chosen = scheme or LEISURE_FEE_SCHEME
    spec = _FEE_SCHEMES.get(chosen) or _FEE_SCHEMES["from_price"]
    amount = Decimal(price)
    rate = Decimal(pct if pct is not None else LEISURE_SERVICE_FEE_PCT)
    fee = Decimal("0") if spec.get("skip") else (amount * rate / Decimal(100)).quantize(Decimal("1"))
    pay_provider = amount - fee if spec["deduct"] else amount
    return {
        "price": amount,
        "pct": rate,
        "fee": fee,
        "discount": fee if spec["deduct"] else Decimal("0"),
        "pay_provider": pay_provider,
        "guest_total": amount if spec["deduct"] or spec.get("skip") else amount + fee,
        "public": bool(spec["public"]),
        "scheme": chosen if chosen in _FEE_SCHEMES else "from_price",
    }


def rub(value) -> str:
    if value is None or value == "":
        return "—"
    return f"{Decimal(value):,.0f}".replace(",", " ") + " ₽"


def pct_label(value) -> str:
    return f"{Decimal(value):f}".rstrip("0").rstrip(".")


def activity_title(code: str | None) -> str:
    row = ACTIVITY_BY_CODE.get(code or "")
    return row[0] if row else "Досуг"


def needs_state(code: str | None) -> bool:
    row = ACTIVITY_BY_CODE.get(code or "")
    return bool(row and row[1])


def join_labels(codes: str | None, table: dict) -> str:
    if not codes:
        return ""
    return ", ".join(table.get(c, c) for c in codes.split(",") if c)
