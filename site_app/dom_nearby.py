"""Места и маршруты каталога рядом с точкой домика.

Только чтение. Если базы нет или запрос упал, страница дома всё равно
открывается: блок «рядом» показывает спокойную заглушку, а не ошибку.
"""
from __future__ import annotations

import logging

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.database import SessionLocal
from app.models import Checkpoint, Trail
from site_app.dom_drive import drive_minutes, format_drive, format_km, haversine_km, rank_by_drive
from site_app.images import srcset as image_srcset
from site_app.images import transform_url
from site_app.router import _place_card_dict, _route_card_dict

log = logging.getLogger("adygid.dom")

# Ближайшие по сфере, потом пересортировка по времени в пути. Коэффициент
# равнины и гор отличается на 8%, поэтому запас по прямой шире, чем итоговый
# список на странице.
_CANDIDATES = 80


def _cover(card: dict) -> dict:
    cover = card.get("cover") or ""
    card["cover_src"] = transform_url(cover, 800) if cover else ""
    card["cover_srcset"] = image_srcset(cover) if cover else ""
    category = card.get("category") or {}
    card["category_name"] = category.get("name") or ""
    card["why"] = card["category_name"]
    return card


def _with_travel(card: dict, origin_lat: float, origin_lon: float, lat: float, lon: float) -> dict | None:
    minutes = drive_minutes(origin_lat, origin_lon, lat, lon)
    if minutes is None:
        return None
    card["drive_min"] = minutes
    card["drive_label"] = format_drive(minutes)
    card["km_label"] = format_km(haversine_km(origin_lat, origin_lon, lat, lon))
    return card


def _place_candidates(db, origin_lat: float, origin_lon: float) -> list[dict]:
    point = func.ST_SetSRID(func.ST_MakePoint(origin_lon, origin_lat), 4326)
    distance = func.ST_DistanceSphere(Checkpoint.geom, point).label("distance_m")
    rows = db.execute(
        select(Checkpoint, distance)
        .where(Checkpoint.show_as_place.is_(True), Checkpoint.is_published.is_(True))
        .options(selectinload(Checkpoint.photos), joinedload(Checkpoint.category))
        .order_by(distance)
        .limit(_CANDIDATES)
    ).unique().all()
    found = []
    for place, _distance_m in rows:
        if place.geom is None:
            continue
        shape = to_shape(place.geom)
        card = _with_travel(_cover(_place_card_dict(place)), origin_lat, origin_lon, shape.y, shape.x)
        if card:
            found.append(card)
    return found


def _route_candidates(db, origin_lat: float, origin_lon: float) -> list[dict]:
    trails = db.execute(
        select(Trail)
        .where(Trail.is_published.is_(True))
        .options(
            selectinload(Trail.photos),
            selectinload(Trail.checkpoints),
            joinedload(Trail.category),
        )
    ).scalars().unique().all()
    found = []
    for trail in trails:
        coords = []
        for point in trail.checkpoints:
            if point.geom is None:
                continue
            shape = to_shape(point.geom)
            coords.append((float(shape.y), float(shape.x)))
        if not coords:
            continue
        lat = sum(item[0] for item in coords) / len(coords)
        lon = sum(item[1] for item in coords) / len(coords)
        card = _with_travel(_cover(_route_card_dict(trail)), origin_lat, origin_lon, lat, lon)
        if card:
            found.append(card)
    return found


def load_catalog(origin_lat: float, origin_lon: float, place_limit: int, route_limit: int) -> dict:
    empty = {"ok": False, "places": [], "routes": [], "categories": []}
    try:
        db = SessionLocal()
    except Exception as exc:
        log.warning("dom catalog: no database session (%s)", exc.__class__.__name__)
        return empty
    try:
        places = rank_by_drive(_place_candidates(db, origin_lat, origin_lon), place_limit)
        routes = rank_by_drive(_route_candidates(db, origin_lat, origin_lon), route_limit)
        categories = []
        for place in places:
            name = place.get("category_name") or ""
            if name and name not in categories:
                categories.append(name)
        return {"ok": True, "places": places, "routes": routes, "categories": categories}
    except Exception as exc:
        log.warning("dom catalog unavailable (%s)", exc.__class__.__name__)
        return empty
    finally:
        db.close()
