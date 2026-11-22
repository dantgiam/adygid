"""Время в пути от домика до места или маршрута.

Формула та же, что в подборе (`site_app/static/podbor-core.js`, `PARAMS` и
`driveMin`): гаверсинус, ×1,3 в горах и ×1,2 если обе точки севернее 44,45°,
50 км/ч, плюс 10 минут на парковку, округление до 5 минут. Это оценка по
прямой, не маршрут навигатора.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

SPEED_KMH = 50
MOUNTAIN_FACTOR = 1.3
PLAIN_FACTOR = 1.2
PLAIN_LAT = 44.45
PARKING_MIN = 10
EARTH_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(h))


def _js_round(value: float) -> int:
    """Math.round: половинки от нуля, не банковское округление Python."""
    if value >= 0:
        return int(value + 0.5)
    return int(value - 0.5)


def drive_minutes(lat1, lon1, lat2, lon2) -> int | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    distance = haversine_km(float(lat1), float(lon1), float(lat2), float(lon2))
    if distance < 0.4:
        return 0
    factor = PLAIN_FACTOR if (lat1 > PLAIN_LAT and lat2 > PLAIN_LAT) else MOUNTAIN_FACTOR
    raw = distance * factor / SPEED_KMH * 60 + PARKING_MIN
    return max(5, _js_round(raw / 5) * 5)


def format_drive(minutes: int) -> str:
    if minutes <= 0:
        return "рядом"
    if minutes < 60:
        return f"≈ {minutes} мин на машине"
    hours, rest = divmod(minutes, 60)
    if rest:
        return f"≈ {hours} ч {rest} мин на машине"
    return f"≈ {hours} ч на машине"


def format_km(distance: float) -> str:
    if distance < 10:
        text = f"{distance:.1f}".replace(".", ",")
    else:
        text = str(int(_js_round(distance)))
    return f"{text} км по прямой"


def rank_by_drive(items: list[dict], limit: int) -> list[dict]:
    ready = [item for item in items if item.get("drive_min") is not None]
    ready.sort(key=lambda item: (item["drive_min"], item.get("name") or ""))
    if limit < 0:
        return ready
    return ready[:limit]
