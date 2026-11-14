"""Подбор маршрута: страница, анонимные ответы, цели Метрики, чужие карточки не трогаем."""
import os
import uuid
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine
from app.main import app
from site_app.podbor_catalog import BEST_PLACES, BEST_ROUTES, UNUSUAL_PLACES, UNUSUAL_ROUTES

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
ROOT = Path(__file__).resolve().parents[1]

PICKER_GOALS = [
    "podbor_cta_click", "podbor_start", "podbor_q1_done", "podbor_q2_done", "podbor_q3_done",
    "podbor_q4_done", "podbor_q5_done", "podbor_q6_done", "podbor_q7_done", "podbor_summary",
    "podbor_plan_build", "podbor_result_few", "podbor_edit", "podbor_refine_start",
    "podbor_like", "podbor_dislike", "place_seen_before", "podbor_plan_like",
    "podbor_plan_dislike", "podbor_card_open", "podbor_feedback_max",
    "podbor_share_click", "podbor_shared_open", "podbor_yamaps_click",
]
SITE_GOALS = [
    "scroll_75", "magnet_click_tg", "place_card_click", "route_card_click",
    "external_map_click", "like_click", "favorite_toggle", "filter_apply",
    "random_place_refresh", "weather_click", "club_page_messenger_click",
]
MONEY_GOALS = [
    "service_view", "booking_start", "booking_submit", "pdf_checkout_start",
    "purchase_success", "ad_partner_click", "paid_route_view", "paid_route_request",
    "lead_magnet_get",
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_editorial_lists_match_approved_counts():
    assert len(BEST_PLACES) + len(BEST_ROUTES) == 15
    assert len(UNUSUAL_PLACES) + len(UNUSUAL_ROUTES) == 26
    assert 50 in BEST_PLACES
    assert 11 not in BEST_ROUTES


def test_catalog_module_does_not_write():
    src = (ROOT / "site_app" / "podbor_catalog.py").read_text(encoding="utf-8")
    assert "db.commit" not in src
    assert "UPDATE " not in src
    assert ".delete(" not in src


def test_home_widget_nav_and_sitemap(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Хотите, подберём для вас маршрут поездки" in home.text
    # «абсолютно бесплатно» выделено маркером, чипы сезонов под плашкой убраны.
    assert '<mark class="podbor-free">абсолютно бесплатно,</mark>' in home.text
    assert "podbor-widget-chips" not in home.text
    assert "под ваши интересы, с учётом времени пребывания" in home.text
    assert 'href="/podbor?src=home_widget"' in home.text
    assert 'href="/podbor"' in home.text
    site = client.get("/sitemap.xml")
    assert "/podbor" in site.text


def test_podbor_page_renders_shell(client):
    page = client.get("/podbor")
    assert page.status_code == 200
    body = page.text
    assert "Адыгея — в вашем темпе" in body
    assert 'id="wizard"' in body
    assert "podbor-core.js" in body
    assert "podbor.js" in body
    assert "Дать обратную связь" in (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")
    assert "https://max.ru/se15002131_bot?start=podbor_" in (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")


def test_live_place_is_linked_from_podbor(client):
    created = client.post(
        "/api/checkpoints",
        json={"name": "Тестовый водопад подбора", "lon": 40.21, "lat": 44.24, "kid_friendly": True, "difficulty": "easy", "is_paid": False},
        auth=AUTH,
    )
    assert created.status_code == 201, created.text
    place_id = created.json()["id"]
    page = client.get("/podbor")
    assert f"/mesta/{place_id}" in page.text
    assert "Тестовый водопад подбора" in page.text


def test_protected_rows_stay_untouched(client):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO trails (id, name, description, is_published, is_paid, difficulty, surface_types, "
            "seasonality, weather_warning, access_type, equipment_tags, kid_friendly, popularity) "
            "VALUES (11, 'Чёртов палец', 'нельзя менять', true, false, 'medium', '{}', "
            "'year_round', false, 'foot_only', '{}', false, 'normal') "
            "ON CONFLICT (id) DO NOTHING"
        ))
        conn.execute(text(
            "INSERT INTO checkpoints (id, name, description, geom, show_as_place, is_published, is_paid, "
            "difficulty, surface_types, seasonality, weather_warning, access_type, equipment_tags, "
            "kid_friendly, popularity, order_index) "
            "VALUES (50, 'Место 50', 'нельзя менять', ST_SetSRID(ST_MakePoint(40.1, 44.2), 4326), true, true, false, "
            "'medium', '{}', 'year_round', false, 'foot_only', '{}', false, 'normal', 0) "
            "ON CONFLICT (id) DO NOTHING"
        ))
        conn.execute(text(
            "SELECT setval(pg_get_serial_sequence('trails','id'), GREATEST((SELECT MAX(id) FROM trails), 1))"
        ))
        conn.execute(text(
            "SELECT setval(pg_get_serial_sequence('checkpoints','id'), GREATEST((SELECT MAX(id) FROM checkpoints), 1))"
        ))
        before = conn.execute(text(
            "SELECT "
            "(SELECT name || '|' || COALESCE(description,'') FROM trails WHERE id = 11), "
            "(SELECT name || '|' || COALESCE(description,'') FROM checkpoints WHERE id = 50)"
        )).one()
    client.get("/podbor")
    with engine.connect() as conn:
        after = conn.execute(text(
            "SELECT "
            "(SELECT name || '|' || COALESCE(description,'') FROM trails WHERE id = 11), "
            "(SELECT name || '|' || COALESCE(description,'') FROM checkpoints WHERE id = 50)"
        )).one()
    assert before == after


def _stats(client):
    response = client.get("/api/podbor/stats", auth=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _sid() -> str:
    return "s" + uuid.uuid4().hex


def test_answers_are_anonymous_and_aggregated(client):
    before = _stats(client)
    family = client.post("/api/podbor/answers", json={
        "session_id": _sid(),
        "events": [
            {"event_type": "answer", "question_id": "party", "answer_code": "family", "skipped": False},
            {"event_type": "answer", "question_id": "season", "answer_code": "summer", "skipped": False},
        ],
    })
    assert family.status_code == 202, family.text
    assert family.json()["stored"] == 2
    solo = client.post("/api/podbor/answers", json={
        "session_id": _sid(),
        "events": [{"event_type": "answer", "question_id": "party", "answer_code": "solo", "skipped": False}],
    })
    assert solo.status_code == 202
    small = client.post("/api/podbor/answers", json={
        "session_id": _sid(),
        "events": [{"event_type": "answer", "question_id": "party", "answer_code": "small", "skipped": False}],
    })
    assert small.status_code == 202
    after = _stats(client)
    assert after["available"] is True
    assert after["with_children"] == before["with_children"] + 2
    assert after["without_children"] == before["without_children"] + 1
    assert after["by_question"]["party"]["family"] >= 1
    assert after["sessions"] >= before["sessions"] + 3


def test_answers_reject_personal_data(client):
    phone = client.post("/api/podbor/answers", json={
        "session_id": "sessReject01",
        "phone": "+79991234567",
        "events": [{"event_type": "answer", "question_id": "party", "answer_code": "solo"}],
    })
    assert phone.status_code == 422
    name = client.post("/api/podbor/answers", json={
        "session_id": "sessReject02",
        "events": [{"event_type": "answer", "question_id": "party", "answer_code": "Иван"}],
    })
    assert name.status_code == 422
    long_number = client.post("/api/podbor/answers", json={
        "session_id": "sessReject03",
        "events": [{"event_type": "answer", "question_id": "base", "answer_code": "79991234567"}],
    })
    assert long_number.status_code == 400


def test_stats_require_admin(client):
    assert client.get("/api/podbor/stats").status_code == 401


def test_missing_table_returns_202(client):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE podbor_answers RENAME TO podbor_answers_hidden"))
    try:
        response = client.post("/api/podbor/answers", json={
            "session_id": "sessMissing1",
            "events": [{"event_type": "answer", "question_id": "pace", "answer_code": "calm", "skipped": False}],
        })
        assert response.status_code == 202, response.text
        assert response.json()["stored"] == 0
        hidden = client.get("/api/podbor/stats", auth=AUTH)
        assert hidden.status_code == 200
        assert hidden.json()["available"] is False
    finally:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE podbor_answers_hidden RENAME TO podbor_answers"))


def test_metrica_goals_are_wired_without_money_events():
    js = "\n".join([
        (ROOT / "site_app" / "static" / "site.js").read_text(encoding="utf-8"),
        (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8"),
    ])
    for name in PICKER_GOALS + SITE_GOALS:
        assert name in js, name
    for name in MONEY_GOALS:
        assert name not in js, name
    assert "magnet_click_telegram" not in js
    assert "function goal" in (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")
    assert "window.adygidGoal" in js
