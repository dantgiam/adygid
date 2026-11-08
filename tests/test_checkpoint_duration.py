"""Длительность точки: пропуск ключа, явный null и число — разные вещи.

Колонка duration_minutes уже nullable. PATCH всё равно не записывал null:
`if body.duration_minutes is not None` не отличает пропуск ключа от
{"duration_minutes": null}. Ответ был 200, минуты и updated_at не менялись,
потому что UPDATE не уходил.

Явный null очищает значение. Тело без ключа старое число сохраняет.
0 остаётся обычным числом. Соседние поля, включая false и 0, не затрагиваются.
Гость при null не видит «0 мин».
"""
import os
import re

os.environ["DATABASE_URL"] = "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adygid-test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine
from app.main import CheckpointUpdate, app
from site_app.router import _duration_label

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])

# «20 мин» и «30 мин» содержат подстроку «0 мин» — ищем именно ноль минут.
_ZERO_MINUTES = re.compile(r"(?<!\d)0 мин")


def _assert_no_zero_minutes(html: str):
    assert _ZERO_MINUTES.search(html) is None
    assert "0 минут" not in html

# Всё, кроме самой длительности и технического updated_at.
_NEIGHBOR_KEYS = (
    "name",
    "description",
    "trail_id",
    "category_id",
    "order_index",
    "show_as_place",
    "is_published",
    "yandex_url",
    "lon",
    "lat",
    "checked_at",
    "difficulty",
    "surface_types",
    "seasonality",
    "weather_warning",
    "access_type",
    "is_paid",
    "price_note",
    "equipment_tags",
    "kid_friendly",
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _neighbors(body):
    return {key: body[key] for key in _NEIGHBOR_KEYS}


def _public_duration(client, cp_id):
    rows = client.get("/api/checkpoints").json()
    match = [row for row in rows if row["id"] == cp_id]
    assert len(match) == 1
    return match[0]["duration_minutes"]


def _freeze_updated_at(cp_id):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE checkpoints SET updated_at = TIMESTAMP '2000-01-01 00:00:00' WHERE id = :id"),
            {"id": cp_id},
        )


def test_model_distinguishes_null_from_omitted_and_column_is_nullable():
    cleared = CheckpointUpdate.model_validate({"duration_minutes": None, "name": "x"})
    assert "duration_minutes" in cleared.model_fields_set
    assert cleared.duration_minutes is None

    omitted = CheckpointUpdate.model_validate({"name": "x"})
    assert "duration_minutes" not in omitted.model_fields_set
    assert omitted.duration_minutes is None

    zero = CheckpointUpdate.model_validate({"duration_minutes": 0})
    assert zero.duration_minutes == 0
    assert "duration_minutes" in zero.model_fields_set

    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'checkpoints' AND column_name = 'duration_minutes'
            """
        )).one()
    assert row.is_nullable == "YES"
    assert row.column_default is None


def test_duration_label_none_is_not_zero_minutes():
    assert _duration_label(None) is None
    assert _duration_label(None) != "0 мин"
    # 0 по-прежнему без подписи, не «0 мин».
    assert _duration_label(0) is None
    assert _duration_label(20) == "20 мин"
    assert _duration_label(90) == "1 ч 30 мин"


def test_checkpoint_duration_patch_omit_null_integer_invalid(client):
    created = client.post(
        "/api/checkpoints",
        json={
            "name": "DurationPatchPlace",
            "description": "исходное описание",
            "lon": 40.15,
            "lat": 44.15,
            "order_index": 0,
            "duration_minutes": 20,
            "show_as_place": True,
            "is_published": True,
            "is_paid": False,
            "kid_friendly": False,
            "weather_warning": False,
            "price_note": "заметка остаётся",
            "difficulty": "easy",
            "yandex_url": "https://yandex.ru/maps/?example",
        },
        auth=AUTH,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    cid = body["id"]
    assert body["duration_minutes"] == 20
    assert body["is_paid"] is False
    assert body["order_index"] == 0
    try:
        omitted = client.patch(
            f"/api/checkpoints/{cid}",
            json={"description": "только текст"},
            auth=AUTH,
        )
        assert omitted.status_code == 200, omitted.text
        body = omitted.json()
        assert body["duration_minutes"] == 20
        assert body["description"] == "только текст"
        assert body["is_paid"] is False
        assert body["kid_friendly"] is False
        assert body["order_index"] == 0
        assert _public_duration(client, cid) == 20

        updated = client.patch(
            f"/api/checkpoints/{cid}",
            json={"duration_minutes": 45},
            auth=AUTH,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["duration_minutes"] == 45
        assert body["description"] == "только текст"
        assert body["is_paid"] is False
        assert body["order_index"] == 0

        zero = client.patch(
            f"/api/checkpoints/{cid}",
            json={"duration_minutes": 0},
            auth=AUTH,
        )
        assert zero.status_code == 200, zero.text
        assert zero.json()["duration_minutes"] == 0
        assert zero.json()["duration_minutes"] is not None
        assert zero.json()["is_paid"] is False

        restored = client.patch(
            f"/api/checkpoints/{cid}",
            json={"duration_minutes": 20},
            auth=AUTH,
        )
        assert restored.status_code == 200, restored.text
        before = restored.json()
        assert before["duration_minutes"] == 20
        neighbors = _neighbors(before)

        _freeze_updated_at(cid)
        untouched = client.patch(f"/api/checkpoints/{cid}", json={}, auth=AUTH)
        assert untouched.status_code == 200, untouched.text
        assert untouched.json()["duration_minutes"] == 20
        assert untouched.json()["updated_at"].startswith("2000-01-01")
        assert _neighbors(untouched.json()) == neighbors

        cleared = client.patch(
            f"/api/checkpoints/{cid}",
            json={"duration_minutes": None},
            auth=AUTH,
        )
        assert cleared.status_code == 200, cleared.text
        body = cleared.json()
        assert body["duration_minutes"] is None
        assert body["duration_minutes"] != 0
        assert not body["updated_at"].startswith("2000-01-01")
        assert _neighbors(body) == neighbors
        assert body["is_paid"] is False
        assert body["kid_friendly"] is False
        assert body["weather_warning"] is False
        assert body["order_index"] == 0
        assert body["show_as_place"] is True
        assert _public_duration(client, cid) is None
        with engine.connect() as conn:
            stored_row = conn.execute(
                text(
                    """
                    SELECT duration_minutes, is_paid, kid_friendly, weather_warning,
                           order_index, show_as_place, district, popularity, price_note
                    FROM checkpoints WHERE id = :id
                    """
                ),
                {"id": cid},
            ).one()
        assert stored_row.duration_minutes is None
        assert stored_row.is_paid is False
        assert stored_row.kid_friendly is False
        assert stored_row.weather_warning is False
        assert stored_row.order_index == 0
        assert stored_row.show_as_place is True
        assert stored_row.district is None
        assert stored_row.popularity == "normal"
        assert stored_row.price_note == "заметка остаётся"

        page = client.get(f"/mesta/{cid}")
        assert page.status_code == 200, page.text
        _assert_no_zero_minutes(page.text)

        # null у соседних полей по-прежнему их не стирает.
        unrelated = client.patch(
            f"/api/checkpoints/{cid}",
            json={"kid_friendly": None, "price_note": None, "description": None, "difficulty": None},
            auth=AUTH,
        )
        assert unrelated.status_code == 200, unrelated.text
        body = unrelated.json()
        assert body["duration_minutes"] is None
        assert body["kid_friendly"] is False
        assert body["price_note"] == "заметка остаётся"
        assert body["description"] == "только текст"
        assert body["difficulty"] == "easy"
        assert body["is_paid"] is False
        assert body["order_index"] == 0

        still_false = client.patch(
            f"/api/checkpoints/{cid}",
            json={"is_paid": False, "show_as_place": False, "order_index": 0},
            auth=AUTH,
        )
        assert still_false.status_code == 200, still_false.text
        body = still_false.json()
        assert body["is_paid"] is False
        assert body["show_as_place"] is False
        assert body["order_index"] == 0
        assert body["duration_minutes"] is None

        _freeze_updated_at(cid)
        for payload in (
            {"duration_minutes": -1},
            {"duration_minutes": "нет"},
            {"duration_minutes": 1.5},
            {"duration_minutes": ""},
        ):
            rejected = client.patch(f"/api/checkpoints/{cid}", json=payload, auth=AUTH)
            assert rejected.status_code == 422, payload
        stored = next(row for row in client.get("/api/checkpoints").json() if row["id"] == cid)
        assert stored["duration_minutes"] is None
        assert stored["updated_at"].startswith("2000-01-01")
        assert stored["is_paid"] is False
        assert stored["description"] == "только текст"
        assert stored["order_index"] == 0
        assert stored["name"] == "DurationPatchPlace"
    finally:
        client.delete(f"/api/checkpoints/{cid}", auth=AUTH)


def test_duration_pages_do_not_show_zero_minutes(client):
    place_null = client.post(
        "/api/checkpoints",
        json={"name": "DurationNullPlace", "lon": 40.16, "lat": 44.16, "duration_minutes": None},
        auth=AUTH,
    )
    place_zero = client.post(
        "/api/checkpoints",
        json={"name": "DurationZeroPlace", "lon": 40.17, "lat": 44.17, "duration_minutes": 0},
        auth=AUTH,
    )
    place_set = client.post(
        "/api/checkpoints",
        json={"name": "DurationSetPlace", "lon": 40.18, "lat": 44.18, "duration_minutes": 20},
        auth=AUTH,
    )
    route_null = client.post("/api/trails", json={"name": "DurationNullRoute"}, auth=AUTH)
    route_zero = client.post(
        "/api/trails", json={"name": "DurationZeroRoute", "duration_minutes": 0}, auth=AUTH,
    )
    route_set = client.post(
        "/api/trails", json={"name": "DurationSetRoute", "duration_minutes": 20}, auth=AUTH,
    )
    created = (place_null, place_zero, place_set, route_null, route_zero, route_set)
    try:
        for response in created:
            assert response.status_code == 201, response.text

        for place in (place_null, place_zero, place_set):
            page = client.get(f"/mesta/{place.json()['id']}")
            assert page.status_code == 200, page.text
            _assert_no_zero_minutes(page.text)

        null_route = client.get(f"/marshruty/{route_null.json()['id']}")
        zero_route = client.get(f"/marshruty/{route_zero.json()['id']}")
        set_route = client.get(f"/marshruty/{route_set.json()['id']}")
        assert "<dt>Длительность</dt><dd>—</dd>" in null_route.text
        assert "<dt>Длительность</dt><dd>—</dd>" in zero_route.text
        assert "<dt>Длительность</dt><dd>20 мин</dd>" in set_route.text
        _assert_no_zero_minutes(null_route.text)
        _assert_no_zero_minutes(zero_route.text)
        _assert_no_zero_minutes(set_route.text)

        admin = client.get("/static/admin.js").text
        public_map = client.get("/map").text
        for source in (admin, public_map):
            assert "duration_minutes || 0" not in source
            assert "duration_minutes ?? 0" not in source
            assert "min == null || !min" in source or "minutes == null || !minutes" in source
    finally:
        for place in (place_null, place_zero, place_set):
            if place.status_code == 201:
                client.delete(f"/api/checkpoints/{place.json()['id']}", auth=AUTH)
        for route in (route_null, route_zero, route_set):
            if route.status_code == 201:
                client.delete(f"/api/trails/{route.json()['id']}", auth=AUTH)
