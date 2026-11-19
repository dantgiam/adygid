"""Партнёры: /partners (301 с /partneram), анкета и админка /admin/partners.

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


def test_page_is_public_noindex_and_sells(client):
    r = client.get("/partners")
    assert r.status_code == 200
    assert "ничего не платите" in r.text or "не платите" in r.text
    assert "без оплаты за рекламу" in r.text
    assert '<meta name="robots" content="noindex, follow">' in r.text
    assert 'id="partner-form"' in r.text and "/soglasie" in r.text and "/privacy" in r.text
    assert 'name="contact_phone"' not in r.text  # по умолчанию телефон — через бота
    assert "5 000 ₽" in r.text and "4 750 ₽" in r.text and "−250 ₽" in r.text
    assert "Реклама" in r.text and "Рекомендуем" in r.text  # тизер с маркировкой
    assert 'id="pt-sticky"' in r.text
    assert "partners.css" in r.text and "partners.js" in r.text
    for c in tx.CATEGORIES:
        assert c["short"] in r.text
    assert 'rel="canonical" href="' in r.text and '/partners"' in r.text


def test_old_url_redirects(client):
    for path in ("/partneram", "/partneram/"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/partners"


def test_page_hidden_from_rest_of_site(client):
    sm = client.get("/sitemap.xml").text
    assert "/partners" not in sm and "/partneram" not in sm
    pages = ["/", "/mesta", "/marshruty", "/stati", "/kuda", "/okrugi", "/voprosy", "/klub", "/podbor", "/robots.txt"]
    pages += [loc.split("</loc>")[0].split("://", 1)[1].split("/", 1)[1] for loc in sm.split("<loc>")[1:40]]
    for path in pages:
        path = path if path.startswith("/") else "/" + path
        r = client.get(path)
        if r.status_code != 200:
            continue
        assert "/partners" not in r.text and "/partneram" not in r.text, path


def test_audience_numbers_are_real_and_rounded_down(client):
    from site_app import partners_audience as pa
    assert pa.round_down(303) == 300 and pa.round_down(1027) == 1000 and pa.round_down(87) == 87
    assert pa.round_down(398) == 350 and pa.round_down(12345) == 12000
    v = pa.view(None)
    raw = pa.load_raw(None)
    assert v["users_30d"] == raw["users_30d"]
    assert int(v["users_30d_label"].rstrip("+").replace("\u00a0", "")) <= raw["users_30d"]
    assert int(v["users_total_label"].rstrip("+").replace("\u00a0", "")) <= raw["users_total"]
    if raw.get("users_prev_30d", 0) >= raw["users_30d"]:
        assert v["growth_pct"] == 0  # роста нет — не показываем
    page = client.get("/partners").text
    assert v["users_30d_label"] in page and v["users_total_label"] in page
    assert "Яндекс Метрики" in page


def test_admin_audience_override(client):
    assert client.get("/admin/partners?tab=audience").status_code == 401
    r = client.get("/admin/partners?tab=audience", auth=AUTH)
    assert r.status_code == 200 and "Цифры для /partners" in r.text
    r = client.post("/admin/partners/audience", auth=AUTH, follow_redirects=False, data={
        "users_30d": "1234", "users_prev_30d": "1000", "users_total": "5678", "visits_30d": "1500",
        "period_from": "2026-12-01", "period_to": "2026-12-30", "search_share_visits": "70",
        "total_since": "2026-07", "top_regions": "Краснодарский край",
    })
    assert r.status_code == 303
    try:
        page = client.get("/partners").text
        assert "1\u00a0200+" in page and "5\u00a0600+" in page and "+23%" in page
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM partner_settings"))
    assert "1\u00a0200+" not in client.get("/partners").text


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


def test_partners_post_rejects_foreign_and_missing_origin(client):
    import asyncio
    import httpx
    from app.main import app
    foreign = client.post(
        "/admin/partners/audience", auth=AUTH, follow_redirects=False,
        headers={"Origin": "https://evil.example"}, data={"users_30d": "10"},
    )
    assert foreign.status_code == 403

    async def _missing():
        # Мимо TestClient: тот подставляет Origin, как браузер на форме админки.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as raw:
            return await raw.post("/admin/partners/audience", auth=AUTH, data={"users_30d": "10"})

    missing = asyncio.run(_missing())
    assert missing.status_code == 403


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


def test_partner_benefits_block_and_no_gold(client):
    page = client.get("/partners").text
    for title in ("Бесплатное размещение на adygid.ru", "Бесплатный поток целевых туристов",
                  "Заявки приходят готовыми", "Без торга и «утечек»", "Отзывы собираем за вас",
                  "Статус раннего партнёра", "Проект растёт — вы вместе с ним", "Без абонплаты"):
        assert title in page, title
    assert "31.12.2026" not in page  # модель без «бесплатно до…»
    css = open(os.path.join(os.path.dirname(__file__), "..", "site_app", "static", "partners.css"), encoding="utf-8").read()
    assert "gold" not in css and "FFD86B" not in css
