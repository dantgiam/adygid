"""«Сохранить план в бота»: сохранение плана по id и чтение для бота."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from site_app.plan_store import fmt_min, fmt_range, yandex_day_url
from site_app.podbor_catalog import catalog_items

ROOT = Path(__file__).resolve().parents[1]
HASH = "plan=winter.short.maykop.family.first.balanced.views,water.2"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def keys():
    db = SessionLocal()
    try:
        items = catalog_items(db)
    finally:
        db.close()
    ks = [f'{x["type"]}:{x["id"]}' for x in items if x.get("lat") is not None]
    if len(ks) < 3:
        pytest.skip("в тестовой базе мало мест")
    return ks


def _body(keys, session="sess-test-1"):
    return {
        "session_id": session,
        "hash": HASH,
        "season": "winter",
        "days": [
            {"area": "maykop", "total_min": 410, "return_drive": 35,
             "stops": [{"k": keys[0], "drive": 20}, {"k": keys[1], "drive": 40, "also": True}]},
            {"area": "lago", "total_min": 300, "stops": [{"k": keys[2], "drive": 0}]},
        ],
    }


def test_save_and_load_plan(client, keys):
    r = client.post("/api/podbor/plans", json=_body(keys))
    assert r.status_code == 201, r.text
    data = r.json()
    pid = data["id"]
    assert len(pid) == 8 and pid.isalnum()
    assert data["max_url"] == f"https://max.ru/se15002131_bot?start=plan_{pid}"
    assert data["tg_url"] == f"https://t.me/adygid_bot?start=plan_{pid}"
    # тот же план из той же вкладки — тот же id
    again = client.post("/api/podbor/plans", json=_body(keys)).json()
    assert again["id"] == pid and again["reused"] is True
    other = client.post("/api/podbor/plans", json=_body(keys, session="sess-test-2")).json()
    assert other["id"] != pid

    plan = client.get(f"/api/podbor/plans/{pid}?bot=1").json()
    assert plan["n_days"] == 2
    assert plan["site_url"].startswith("https://www.adygid.ru/podbor#plan=")
    d1 = plan["days"][0]
    assert d1["area_name"] == "Майкоп" and d1["total"] == "6 ч 50 мин"
    assert len(d1["stops"]) == 2 and d1["stops"][0]["url"].startswith("https://www.adygid.ru/")
    assert d1["stops"][1]["also"] is True
    assert d1["map_url"].startswith("https://yandex.ru/maps/?rtext=")
    assert plan["days"][1]["map_url"].startswith("https://yandex.ru/maps/?pt=")


def test_rejects_bad_input(client, keys):
    assert client.post("/api/podbor/plans", json=dict(_body(keys), hash="javascript:alert(1)")).status_code == 400
    bad = _body(keys)
    bad["days"][0]["stops"][0]["k"] = "place:999999"
    bad["days"][0]["stops"][1]["k"] = "place:999998"
    bad["days"][1]["stops"][0]["k"] = "route:999999"
    assert client.post("/api/podbor/plans", json=bad).status_code == 400
    extra = _body(keys)
    extra["days"][0]["stops"][0]["name"] = "<script>"
    assert client.post("/api/podbor/plans", json=extra).status_code == 422
    assert client.post("/api/podbor/plans", json=dict(_body(keys), days=[{"stops": []}] * 8)).status_code == 422
    assert client.get("/api/podbor/plans/nope!").status_code == 404
    assert client.get("/api/podbor/plans/zzzzzzzz").status_code == 404


def test_formatters_match_core():
    assert fmt_min(95) == "1 ч 35 мин" and fmt_min(40) == "40 мин" and fmt_min(120) == "2 ч"
    assert fmt_range({"min": 60, "typ": 90, "max": 120, "source": "estimate"}) == "1–2 ч"
    assert fmt_range({"min": 20, "typ": 30, "max": 45}) == "20–45 мин"
    assert fmt_range({"min": 90, "typ": 90, "max": 90, "source": "card"}) == "1 ч 30 мин"
    assert yandex_day_url([(44.1, 40.2), (44.3, 40.4)]) == "https://yandex.ru/maps/?rtext=44.1,40.2~44.3,40.4&rtt=auto"


def test_plan_screen_has_bot_chooser():
    js = (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")
    for needle in ('data-act="save"', '"savebot"', "plan_save_max", "plan_save_tg", "/api/podbor/plans",
                   "podbor_save_click", "podbor_share_click"):
        assert needle in js, needle
    css = (ROOT / "site_app" / "static" / "podbor.css").read_text(encoding="utf-8")
    assert ".a3-save-btn.is-max" in css and ".a3-save-btn.is-tg" in css
