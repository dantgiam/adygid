"""Каталог для подборщика: живые места и маршруты + утверждённая разметка.

Фото, названия, координаты, длительность и сложность читаются из базы.
Теги, район, зимний допуск, коляска и списки «Лучшее» / «Необычное»
считаются теми же правилами, что в разметке v2. Списки утверждены как есть.

Модуль только читает. Маршрут 11 «Чёртов палец» и место 50 не изменяются:
они могут попасть в выдачу, но ни одно поле в базе не переписывается.
"""
import json
import re
import time
from pathlib import Path

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Checkpoint, Trail

_COPY_PATH = Path(__file__).resolve().parent / "data" / "podbor_copy.json"
_COPY_CACHE: dict = {"value": None}

# Якоря районов — те же, что в podbor-core.js (оценка дороги, не навигация).
AREAS = {
    "maykop": ("Майкоп", 44.605, 40.100),
    "tulsky": ("Тульский и Цветочный", 44.490, 40.160),
    "khadzhokh": ("Каменномостский (Хаджох)", 44.295, 40.185),
    "dakhovskaya": ("Даховская", 44.235, 40.210),
    "lago": ("Лаго-Наки", 44.085, 40.015),
    "valley": ("Хамышки и Гранитный каньон", 44.125, 40.110),
    "guzeripl": ("Гузерипль", 44.000, 40.136),
    "sakhray": ("Сахрай", 44.174, 40.300),
    "pobeda": ("Победа", 44.288, 40.330),
    "novosvobodnaya": ("Новосвободная", 44.417, 40.346),
    "north": ("Гончарка (равнина)", 44.807, 39.947),
}

# Утверждённые черновые списки: 12+3 «Лучшее», 18+8 «Необычное».
BEST_PLACES = {24, 40, 55, 25, 52, 48, 50, 56, 75, 67, 30, 57}
UNUSUAL_PLACES = {87, 44, 88, 89, 90, 94, 91, 81, 79, 42, 99, 51, 60, 36, 86, 93, 41}
BEST_ROUTES = {12, 16, 13}
UNUSUAL_ROUTES = {22, 26, 27, 28, 29, 20, 25, 24, 30}
INDOOR = {45, 62, 69, 76, 77, 83, 80}
STEP_V1 = {24, 25, 40, 44, 50, 58, 59, 61, 73, 74, 78, 82, 84}
WINTER_UNKNOWN_PLACES = {84, 29, 56, 59, 61, 66, 75, 73, 74}
WINTER_UNKNOWN_ROUTES = {23, 24, 15, 11, 10}
STROLLER_NO_ROUTES = {10, 11, 15, 19, 23, 24}
FALLBACK_STOPS = {18: [69, 70, 76, 77, 83], 19: [78, 71], 20: [79], 21: [80, 72, 68], 22: [81, 82, 36, 87], 23: [84], 24: [85]}

CAT_TAGS = {
    "Пещера": ["caves"],
    "Водопад": ["water"],
    "Каньон / ущелье": ["water"],
    "Река / озеро": ["water"],
    "Смотровая": ["views"],
    "Плато / гора": ["views"],
    "Скала-памятник": ["views"],
    "Музей": ["culture"],
    "Монастырь / храм": ["culture"],
    "Дольмен": ["culture"],
    "Археологический объект": ["culture"],
    "Аул / этнообъект": ["culture", "familyfun"],
    "Термальный источник": ["thermal"],
    "Заповедник / парк": ["familyfun"],
}
NAME_TAGS = [
    ("водопад|каньон|теснин|ущель|лагун|сплав", "water"),
    ("пещер|грот", "caves"),
    ("смотров|панорам|плато|гора |гора$|скала|перевал|канатн|вершин", "views"),
    ("музе|галере|мечет|дольмен|монастыр|пустын|крест|печи|чай|мост", "culture"),
    ("терм|аква|кедров|псыгуп", "thermal"),
    ("вольер|парк|сыровар|ферм|аммонит|беловод|чай|канатн", "familyfun"),
]
TIERS = [
    ("quick", 20, 30, 45),
    ("short", 60, 90, 120),
    ("medium", 120, 180, 240),
    ("half", 240, 300, 360),
    ("full", 360, 480, 600),
]

_cache: dict = {"items": None, "at": 0.0}
_TTL_S = 120


def invalidate_podbor_cache() -> None:
    _cache["items"] = None
    _cache["at"] = 0.0


def load_copy() -> dict:
    if _COPY_CACHE["value"] is None:
        _COPY_CACHE["value"] = json.loads(_COPY_PATH.read_text(encoding="utf-8"))
    return _COPY_CACHE["value"]


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _km(lat1, lon1, lat2, lon2) -> float:
    from math import asin, cos, radians, sin, sqrt
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(h))


def area_of(lat, lon) -> str:
    if lat is None or lon is None:
        return "other"
    return min(AREAS, key=lambda k: _km(lat, lon, AREAS[k][1], AREAS[k][2]))


def tags_for(name: str, category: str) -> list:
    out = list(CAT_TAGS.get(category, []))
    low = (name or "").lower()
    for rx, tag in NAME_TAGS:
        if tag not in out and re.search(rx, low):
            out.append(tag)
    return out


def _tier_of(minutes: int) -> str:
    if minutes <= 45:
        return "quick"
    if minutes <= 120:
        return "short"
    if minutes <= 240:
        return "medium"
    if minutes <= 360:
        return "half"
    return "full"


def _est_tier(kind: str, category: str, difficulty: str, access: str) -> str:
    if kind == "route":
        return {"hard": "half", "extreme": "full"}.get(difficulty, "medium")
    if difficulty == "hard":
        return "medium" if category == "Пещера" else "half"
    if difficulty == "extreme":
        return "full"
    if category in ("Музей", "Монастырь / храм", "Дольмен", "Археологический объект", "Скала-памятник", "Смотровая"):
        return "short" if access in ("foot_only", "hike") else "quick"
    return "short"


def _visit(minutes, tier_id: str, kind: str) -> dict:
    if minutes:
        factor = 0.75 if kind == "place" else 0.8
        note = "по данным карточки сайта" if kind == "place" else "по данным маршрута на сайте"
        return {
            "min": round(minutes * factor),
            "typ": minutes,
            "max": round(minutes * 1.25),
            "source": "card",
            "note": note,
        }
    tier = next(t for t in TIERS if t[0] == tier_id)
    note = "оценка по типу места и сложности" if kind == "place" else "оценка по сложности маршрута"
    return {"min": tier[1], "typ": tier[2], "max": tier[3], "source": "estimate", "note": note}


def _coords(obj):
    if obj is None or obj.geom is None:
        return None, None
    shp = to_shape(obj.geom)
    return float(shp.y), float(shp.x)


def _photo(photos) -> tuple:
    if not photos:
        return "", ""
    ph = photos[0]
    url = ph.thumb_url or ph.url or ""
    caption = ph.caption or "Фотография из карточки АдыГида"
    return url, caption


def _editorial(kind: str, item_id: int) -> str:
    if kind == "place":
        if item_id in BEST_PLACES:
            return "best"
        if item_id in UNUSUAL_PLACES:
            return "unusual"
    else:
        if item_id in BEST_ROUTES:
            return "best"
        if item_id in UNUSUAL_ROUTES:
            return "unusual"
    return ""


def _winter_place(place: Checkpoint, desc: str, difficulty: str, access: str) -> str:
    season = place.seasonality or "year_round"
    if season == "summer_only":
        return "no"
    if re.search(r"сух\w* бесснеж|только.{0,18}сух.{0,30}снег", desc, re.I):
        return "no"
    if difficulty in ("hard", "extreme") or place.id in WINTER_UNKNOWN_PLACES:
        return "unknown"
    if access in ("foot_only", "hike", "high_clearance"):
        return "unknown"
    return "yes"


def _stroller_place(place: Checkpoint, desc: str, access: str) -> str:
    surf = set(place.surface_types or [])
    low = (place.name or "").lower()
    if re.search(r"сплав|рафтинг", low):
        return "no"
    if place.id in STEP_V1 or re.search(r"ступен|лестниц", desc.lower()):
        return "no"
    if access in ("foot_only", "hike") or "scramble" in surf or "trail" in surf:
        return "no"
    if access == "paved" and surf and surf <= {"asphalt"}:
        return "maybe"
    return "unknown"


def _place_item(place: Checkpoint) -> dict:
    desc = _clean(place.description)
    category = place.category.name if place.category else ""
    difficulty = place.difficulty or "medium"
    access = place.access_type or "foot_only"
    lat, lon = _coords(place)
    image, caption = _photo(place.photos)
    minutes = place.duration_minutes
    tier = _tier_of(minutes) if minutes else _est_tier("place", category, difficulty, access)
    visit = _visit(minutes, tier, "place")
    return {
        "type": "place",
        "id": place.id,
        "name": place.name,
        "url": f"/mesta/{place.id}",
        "lat": lat,
        "lon": lon,
        "area": area_of(lat, lon),
        "tags": tags_for(place.name, category),
        "difficulty": difficulty,
        "kid": bool(place.kid_friendly),
        "winter_ok": _winter_place(place, desc, difficulty, access),
        "stroller": _stroller_place(place, desc, access),
        "visit": visit,
        "checked": bool(place.checked_at),
        "indoor": place.id in INDOOR,
        "editorial": _editorial("place", place.id),
        "is_paid": place.is_paid,
        "price_note": place.price_note or "",
        "image": image,
        "photoCaption": caption,
        "stops": [],
    }


def _route_item(trail: Trail, places: dict) -> dict:
    desc = _clean(trail.description)
    raw = trail.description or ""
    category = trail.category.name if trail.category else ""
    difficulty = trail.difficulty or "medium"
    stops = [cp.id for cp in sorted(trail.checkpoints, key=lambda c: c.order_index or 0)]
    if not stops:
        linked = [int(m) for m in re.findall(r"/mesta/(\d+)", raw)]
        stops = [i for i in dict.fromkeys(linked) if i in places] or list(FALLBACK_STOPS.get(trail.id, []))
    coords = []
    for cp in trail.checkpoints:
        lat, lon = _coords(cp)
        if lat is not None:
            coords.append((lat, lon))
    if not coords:
        for sid in stops:
            p = places.get(sid)
            if p and p.get("lat") is not None:
                coords.append((p["lat"], p["lon"]))
    if coords:
        lat = sum(c[0] for c in coords) / len(coords)
        lon = sum(c[1] for c in coords) / len(coords)
    else:
        lat, lon = None, None
    tags = []
    for sid in stops:
        for tag in (places.get(sid) or {}).get("tags") or []:
            if tag not in tags:
                tags.append(tag)
    for tag in tags_for(trail.name, ""):
        if tag not in tags:
            tags.append(tag)
    minutes = trail.duration_minutes
    tier = _tier_of(minutes) if minutes else _est_tier("route", category, difficulty, trail.access_type or "")
    visit = _visit(minutes, tier, "route")
    if (trail.seasonality or "") == "summer_only" or re.search(r"сух\w* бесснеж|только.{0,18}сух.{0,30}снег", desc, re.I):
        winter = "no"
    elif trail.id in WINTER_UNKNOWN_ROUTES or difficulty in ("hard", "extreme"):
        winter = "unknown"
    else:
        winters = [places[i]["winter_ok"] for i in stops if i in places]
        winter = "yes" if winters and all(v == "yes" for v in winters) else "unknown"
    if trail.id in STROLLER_NO_ROUTES or any((places.get(i) or {}).get("stroller") == "no" for i in stops):
        stroller = "no"
    else:
        stroller = "unknown"
    image, caption = _photo(trail.photos)
    return {
        "type": "route",
        "id": trail.id,
        "name": trail.name,
        "url": f"/marshruty/{trail.id}",
        "lat": lat,
        "lon": lon,
        "area": area_of(lat, lon),
        "tags": tags,
        "difficulty": difficulty,
        "kid": bool(trail.kid_friendly),
        "winter_ok": winter,
        "stroller": stroller,
        "visit": visit,
        "checked": bool(trail.checked_at),
        "indoor": False,
        "editorial": _editorial("route", trail.id),
        "is_paid": trail.is_paid,
        "price_note": trail.price_note or "",
        "image": image,
        "photoCaption": caption,
        "stops": stops,
    }


def build_catalog(db: Session) -> list:
    """Собрать каталог. Только SELECT."""
    places_rows = db.execute(
        select(Checkpoint)
        .where(Checkpoint.show_as_place == True, Checkpoint.is_published == True)
        .options(selectinload(Checkpoint.photos), joinedload(Checkpoint.category))
    ).scalars().unique().all()
    place_items = [_place_item(p) for p in places_rows]
    by_id = {p["id"]: p for p in place_items}
    trails = db.execute(
        select(Trail)
        .where(Trail.is_published == True)
        .options(
            selectinload(Trail.photos),
            joinedload(Trail.category),
            selectinload(Trail.checkpoints),
        )
    ).scalars().unique().all()
    route_items = [_route_item(t, by_id) for t in trails]
    return place_items + route_items


def catalog_items(db: Session) -> list:
    now = time.monotonic()
    if _cache["items"] is not None and now - _cache["at"] < _TTL_S:
        return _cache["items"]
    items = build_catalog(db)
    _cache["items"] = items
    _cache["at"] = now
    return items


def script_json(data) -> str:
    """JSON для вставки в <script>: без сырого </, чтобы тег не закрылся раньше времени."""
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
