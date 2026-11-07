"""Стоимость места и маршрута: true / false / неизвестно.

PATCH с {"is_paid": null} сбрасывает статус в «не проверено».
Тело без ключа is_paid прежнее значение не меняет.
Неизвестный статус не рисуется как «Платно», «Бесплатно» или ноль.
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
from app.main import CheckpointUpdate, TrailUpdate, _relax_is_paid_column, app
from site_app.router import _price_label

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _spec(html: str) -> str:
    start = html.find('<aside class="spec-box">')
    assert start != -1, "spec box missing"
    end = html.find("</aside>", start)
    return html[start:end]


def _card(html: str, name: str) -> str:
    marker = f"<h3>{name}</h3>"
    at = html.find(marker)
    assert at != -1, name
    start = html.rfind('<a class="card"', 0, at)
    end = html.find("</a>", at)
    return html[start:end]


def _post_place(client, name, is_paid, **extra):
    body = {"name": name, "lon": extra.pop("lon", 40.1), "lat": extra.pop("lat", 44.1)}
    if is_paid is not _OMIT:
        body["is_paid"] = is_paid
    body.update(extra)
    response = client.post("/api/checkpoints", json=body, auth=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


def _post_route(client, name, is_paid, **extra):
    body = {"name": name}
    if is_paid is not _OMIT:
        body["is_paid"] = is_paid
    body.update(extra)
    response = client.post("/api/trails", json=body, auth=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


class _Omit:
    pass


_OMIT = _Omit()


def test_price_label_three_states():
    assert _price_label(True, None) == "Платно"
    assert _price_label(True, "300 ₽") == "300 ₽"
    assert _price_label(False, None) == "Бесплатно"
    assert _price_label(False, "устаревшая пометка") == "Бесплатно"
    # Неизвестная стоимость не превращается в «бесплатно», ноль или текст пометки.
    assert _price_label(None, None) is None
    assert _price_label(None, "300 ₽") is None
    assert _price_label(None, "0") is None


def test_patch_model_distinguishes_null_from_omitted():
    cleared = CheckpointUpdate.model_validate({"is_paid": None, "name": "x"})
    assert "is_paid" in cleared.model_fields_set
    assert cleared.is_paid is None

    omitted = CheckpointUpdate.model_validate({"name": "x"})
    assert "is_paid" not in omitted.model_fields_set

    trail = TrailUpdate.model_validate({"is_paid": None})
    assert "is_paid" in trail.model_fields_set
    assert trail.is_paid is None
    assert "is_paid" not in TrailUpdate.model_validate({}).model_fields_set


def test_is_paid_column_nullable_without_false_default():
    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT table_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE column_name = 'is_paid'
              AND table_name IN ('trails', 'checkpoints')
            ORDER BY table_name
            """
        )).all()
    assert [row.table_name for row in rows] == ["checkpoints", "trails"]
    for row in rows:
        assert row.is_nullable == "YES", row
        assert row.column_default is None, row


def test_checkpoint_patch_null_clears_and_omit_keeps(client):
    created = _post_place(
        client, "CostPatchPlace", True,
        lon=40.11, lat=44.11,
        price_note="заметка о цене",
        kid_friendly=True,
        description="исходное",
    )
    cid = created["id"]
    try:
        assert created["is_paid"] is True

        omitted = client.patch(
            f"/api/checkpoints/{cid}",
            json={"description": "только текст"},
            auth=AUTH,
        )
        assert omitted.status_code == 200, omitted.text
        body = omitted.json()
        assert body["is_paid"] is True
        assert body["price_note"] == "заметка о цене"
        assert body["kid_friendly"] is True
        assert body["description"] == "только текст"

        cleared = client.patch(f"/api/checkpoints/{cid}", json={"is_paid": None}, auth=AUTH)
        assert cleared.status_code == 200, cleared.text
        body = cleared.json()
        assert body["is_paid"] is None
        # null у соседних полей по-прежнему не стирает их: сброс только у is_paid.
        assert body["price_note"] == "заметка о цене"
        assert body["kid_friendly"] is True

        unrelated_nulls = client.patch(
            f"/api/checkpoints/{cid}",
            json={"kid_friendly": None, "price_note": None},
            auth=AUTH,
        )
        assert unrelated_nulls.status_code == 200, unrelated_nulls.text
        body = unrelated_nulls.json()
        assert body["is_paid"] is None
        assert body["kid_friendly"] is True
        assert body["price_note"] == "заметка о цене"

        freed = client.patch(f"/api/checkpoints/{cid}", json={"is_paid": False}, auth=AUTH)
        assert freed.json()["is_paid"] is False
        paid_again = client.patch(f"/api/checkpoints/{cid}", json={"is_paid": True}, auth=AUTH)
        assert paid_again.json()["is_paid"] is True

        # Повторный явный null после true снова неизвестен, а не false.
        cleared_again = client.patch(f"/api/checkpoints/{cid}", json={"is_paid": None}, auth=AUTH)
        assert cleared_again.json()["is_paid"] is None
    finally:
        client.delete(f"/api/checkpoints/{cid}", auth=AUTH)


def test_trail_patch_null_clears_and_omit_keeps(client):
    created = _post_route(
        client, "CostPatchRoute", False,
        price_note="не должна всплыть",
        kid_friendly=True,
    )
    tid = created["id"]
    try:
        assert created["is_paid"] is False

        omitted = client.patch(f"/api/trails/{tid}", json={"description": "правка"}, auth=AUTH)
        assert omitted.status_code == 200, omitted.text
        body = omitted.json()
        assert body["is_paid"] is False
        assert body["price_note"] == "не должна всплыть"
        assert body["kid_friendly"] is True

        cleared = client.patch(f"/api/trails/{tid}", json={"is_paid": None}, auth=AUTH)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["is_paid"] is None
        assert cleared.json()["price_note"] == "не должна всплыть"

        paid = client.patch(f"/api/trails/{tid}", json={"is_paid": True}, auth=AUTH)
        assert paid.json()["is_paid"] is True
    finally:
        client.delete(f"/api/trails/{tid}", auth=AUTH)


def test_new_draft_without_is_paid_is_unknown_not_free(client):
    place = _post_place(client, "CostDraftPlace", _OMIT, lon=40.12, lat=44.12)
    route = _post_route(client, "CostDraftRoute", _OMIT)
    explicit_null = _post_place(client, "CostExplicitNullPlace", None, lon=40.13, lat=44.13)
    explicit_free = _post_place(client, "CostExplicitFreePlace", False, lon=40.14, lat=44.14)
    try:
        assert place["is_paid"] is None
        assert route["is_paid"] is None
        assert explicit_null["is_paid"] is None
        assert explicit_free["is_paid"] is False

        for path in (f"/mesta/{place['id']}", f"/marshruty/{route['id']}", f"/mesta/{explicit_null['id']}"):
            page = client.get(path)
            assert page.status_code == 200, page.text
            spec = _spec(page.text)
            assert "<dt>Стоимость</dt>" not in spec
            assert "Бесплатно" not in spec
            assert "Платно" not in spec
            assert "isAccessibleForFree" not in page.text

        free_page = client.get(f"/mesta/{explicit_free['id']}")
        assert "<dt>Стоимость</dt><dd>Бесплатно</dd>" in free_page.text
        assert re.search(r'"isAccessibleForFree"\s*:\s*true', free_page.text)
    finally:
        client.delete(f"/api/checkpoints/{place['id']}", auth=AUTH)
        client.delete(f"/api/trails/{route['id']}", auth=AUTH)
        client.delete(f"/api/checkpoints/{explicit_null['id']}", auth=AUTH)
        client.delete(f"/api/checkpoints/{explicit_free['id']}", auth=AUTH)


def test_render_paid_free_and_unknown(client):
    paid = _post_place(client, "CostRenderPaid", True, lon=40.21, lat=44.21)
    noted = _post_place(
        client, "CostRenderNoted", True,
        lon=40.22, lat=44.22, price_note="300 ₽",
    )
    free = _post_place(client, "CostRenderFree", False, lon=40.23, lat=44.23)
    unknown = _post_place(
        client, "CostRenderUnknown", None,
        lon=40.24, lat=44.24, price_note="эту пометку гость не видит",
    )
    paid_route = _post_route(client, "CostRenderPaidRoute", True)
    free_route = _post_route(client, "CostRenderFreeRoute", False)
    unknown_route = _post_route(client, "CostRenderUnknownRoute", None, price_note="скрытая пометка")
    ids = [paid, noted, free, unknown]
    route_ids = [paid_route, free_route, unknown_route]
    try:
        paid_page = client.get(f"/mesta/{paid['id']}")
        assert "<dt>Стоимость</dt><dd>Платно</dd>" in paid_page.text
        assert re.search(r'"isAccessibleForFree"\s*:\s*false', paid_page.text)
        assert "Бесплатно" not in _spec(paid_page.text)

        noted_page = client.get(f"/mesta/{noted['id']}")
        assert "<dt>Стоимость</dt><dd>300 ₽</dd>" in noted_page.text
        assert "Бесплатно" not in _spec(noted_page.text)
        assert re.search(r'"isAccessibleForFree"\s*:\s*false', noted_page.text)

        free_page = client.get(f"/mesta/{free['id']}")
        assert "<dt>Стоимость</dt><dd>Бесплатно</dd>" in free_page.text
        assert re.search(r'"isAccessibleForFree"\s*:\s*true', free_page.text)
        assert "Платно" not in _spec(free_page.text)

        unknown_page = client.get(f"/mesta/{unknown['id']}")
        unknown_spec = _spec(unknown_page.text)
        assert "<dt>Стоимость</dt>" not in unknown_spec
        assert "Бесплатно" not in unknown_spec
        assert "Платно" not in unknown_spec
        assert "эту пометку гость не видит" not in unknown_spec
        assert "isAccessibleForFree" not in unknown_page.text

        paid_route_page = client.get(f"/marshruty/{paid_route['id']}")
        assert "<dt>Стоимость</dt><dd>Платно</dd>" in paid_route_page.text
        free_route_page = client.get(f"/marshruty/{free_route['id']}")
        assert "<dt>Стоимость</dt><dd>Бесплатно</dd>" in free_route_page.text
        unknown_route_page = client.get(f"/marshruty/{unknown_route['id']}")
        unknown_route_spec = _spec(unknown_route_page.text)
        assert "<dt>Стоимость</dt>" not in unknown_route_spec
        assert "Бесплатно" not in unknown_route_spec
        assert "Платно" not in unknown_route_spec
        assert "скрытая пометка" not in unknown_route_spec

        listing = client.get("/mesta").text
        assert ">Платно</span>" in _card(listing, "CostRenderPaid")
        assert ">Платно</span>" in _card(listing, "CostRenderNoted")
        free_card = _card(listing, "CostRenderFree")
        unknown_card = _card(listing, "CostRenderUnknown")
        assert "Платно" not in free_card
        assert "Бесплатно" not in free_card
        assert "Платно" not in unknown_card
        assert "Бесплатно" not in unknown_card
        assert "эту пометку гость не видит" not in unknown_card

        only_free = client.get("/mesta?paid=0").text
        assert "CostRenderFree" in only_free
        assert "CostRenderPaid" not in only_free
        assert "CostRenderNoted" not in only_free
        assert "CostRenderUnknown" not in only_free

        only_paid = client.get("/mesta?paid=1").text
        assert "CostRenderPaid" in only_paid
        assert "CostRenderNoted" in only_paid
        assert "CostRenderFree" not in only_paid
        assert "CostRenderUnknown" not in only_paid
    finally:
        for row in ids:
            client.delete(f"/api/checkpoints/{row['id']}", auth=AUTH)
        for row in route_ids:
            client.delete(f"/api/trails/{row['id']}", auth=AUTH)


def _place_flags(client):
    return {row["id"]: row["is_paid"] for row in client.get("/api/checkpoints").json()}


def test_relax_migration_keeps_existing_booleans(client):
    """Старое ограничение NOT NULL DEFAULT false снимается без UPDATE значений."""
    paid = _post_place(client, "CostKeepPaid", True, lon=40.31, lat=44.31)
    free = _post_place(client, "CostKeepFree", False, lon=40.32, lat=44.32)
    route = _post_route(client, "CostKeepRoute", True)
    unknown = None
    try:
        with engine.begin() as conn:
            for table in ("checkpoints", "trails"):
                conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN is_paid SET DEFAULT false"))
                conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN is_paid SET NOT NULL"))
        assert _place_flags(client)[paid["id"]] is True
        assert _place_flags(client)[free["id"]] is False
        assert client.get(f"/api/trails/{route['id']}").json()["is_paid"] is True

        with engine.begin() as conn:
            _relax_is_paid_column(conn, "checkpoints")
            _relax_is_paid_column(conn, "trails")

        assert _place_flags(client)[paid["id"]] is True
        assert _place_flags(client)[free["id"]] is False
        assert client.get(f"/api/trails/{route['id']}").json()["is_paid"] is True

        unknown = _post_place(client, "CostKeepUnknown", None, lon=40.33, lat=44.33)
        assert unknown["is_paid"] is None
    finally:
        with engine.begin() as conn:
            _relax_is_paid_column(conn, "checkpoints")
            _relax_is_paid_column(conn, "trails")
        for row in (paid, free, unknown):
            if row is not None:
                client.delete(f"/api/checkpoints/{row['id']}", auth=AUTH)
        client.delete(f"/api/trails/{route['id']}", auth=AUTH)
