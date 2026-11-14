"""Партнёры: /partneram, анкета и админка /admin/partners.

Главное: партнёр ничего не платит; без PARTNER_PD_IN_SITE_DB телефон и имя
в базу сайта не пишутся (152-ФЗ, база не в РФ); в лидах нет ПД туриста;
сервисный сбор и скидка по умолчанию считаются от цены партнёра.
"""
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adygid-test"
os.environ.pop("PARTNER_PD_IN_SITE_DB", None)
os.environ.pop("BOT_API_TOKEN", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine
from app.main import app
from site_app import partners_taxonomy as tx

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])

GOOD = {
    "company": "Тестовый рафтинг", "category": "adventure", "subcategory": "rafting",
    "location": "Даховская", "services": "Сплав 8 км", "discount": "5%",
    "seasons": ["summer", "bogus"], "lead_channels": ["max"], "consent": True,
    "contact_name": "Иван", "contact_phone": "+7 900 000-00-00", "contact_messenger": "@ivan",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM partner_leads; DELETE FROM partners; DELETE FROM partner_applications"))
        yield c


def test_taxonomy_shape():
    assert 7 <= len(tx.CATEGORIES) <= 9
    codes = [c["code"] for c in tx.CATEGORIES]
    assert len(codes) == len(set(codes))
    for c in tx.CATEGORIES:
        assert c["subs"], c["code"]
    assert tx.valid_pair("rental", "tubing") and not tx.valid_pair("rental", "rafting")


def test_page_is_public_and_not_in_nav(client):
    r = client.get("/partneram")
    assert r.status_code == 200
    assert "ничего не платите" in r.text
    assert 'id="partner-form"' in r.text and "/soglasie" in r.text and "/privacy" in r.text
    assert 'name="contact_phone"' not in r.text  # по умолчанию телефон — через бота
    home = client.get("/")
    assert "/partneram" not in home.text


def test_apply_does_not_store_pd_by_default(client):
    r = client.post("/api/partners/apply", json=GOOD)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["contacts_via_bot"] is True
    assert data["bot"]["max"].endswith("start=partner_" + data["code"])
    with engine.begin() as conn:
        row = conn.execute(text("SELECT contact_name, contact_phone, contact_messenger, seasons, discount FROM partner_applications WHERE code=:c"), {"c": data["code"]}).one()
    assert row[:3] == (None, None, None)
    assert row[3] == "summer" and row[4] == "5%"


def test_apply_validation(client):
    assert client.post("/api/partners/apply", json={**GOOD, "subcategory": "tubing"}).status_code == 400
    assert client.post("/api/partners/apply", json={**GOOD, "consent": False}).status_code == 400
    bad = dict(GOOD); bad.pop("discount")
    assert client.post("/api/partners/apply", json=bad).status_code == 422


def test_admin_requires_auth(client):
    assert client.get("/admin/partners").status_code == 401
    assert client.get("/admin/partners", auth=AUTH).status_code == 200


def test_convert_and_leads(client):
    with engine.begin() as conn:
        app_id = conn.execute(text("SELECT id FROM partner_applications ORDER BY id LIMIT 1")).scalar()
    r = client.get(f"/admin/partners/applications/{app_id}", auth=AUTH)
    assert r.status_code == 200 and "Бот не подключён" in r.text
    r = client.post(f"/admin/partners/applications/{app_id}/convert", auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    pid = int(r.headers["location"].split("/")[3].split("?")[0])
    r = client.post(f"/admin/partners/{pid}/leads", auth=AUTH, follow_redirects=False,
                    data={"inbox_ref": "3f0c9a52", "service": "Сплав", "status": "completed",
                          "provider_price": "5000", "fee_status": "paid"})
    assert r.status_code == 303
    with engine.begin() as conn:
        lead = conn.execute(text("SELECT service_fee_pct, service_fee_amount, discount_amount FROM partner_leads WHERE partner_id=:p"), {"p": pid}).one()
        contacts = conn.execute(text("SELECT contacts FROM partners WHERE id=:p"), {"p": pid}).scalar()
    assert float(lead[0]) == 5 and float(lead[1]) == 250 and float(lead[2]) == 250
    assert "phone" not in contacts and contacts["bot_ref"].startswith("partner_")
    page = client.get("/admin/partners?tab=leads", auth=AUTH).text
    assert "250 ₽" in page and "4 750 ₽" in page
