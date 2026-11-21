"""Досуг: заявка, модерация, слаг, сбор 5%, поля по типу и защита формы.

Сбор жилья не меняется. Черновик не открывается и не попадает в sitemap.
Номера документов на публичную страницу не выходят.
"""
import io
import os
import re
import uuid
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.database import engine
from app.main import app
from app.models import LeisureOffer, Partner
from site_app import leisure as leisure_mod
from site_app import leisure_catalog as cat
from site_app.leisure import validate_offer
from site_app.leisure_photos import MIN_WIDTH, PhotoError, prepare_image
from site_app.router import SITE_URL

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
ORIGIN = {"Origin": "http://testserver"}
SECRET_PHONE = "+7 900 555-19-19"
SECRET_NAME = "Секретноеимядосуг"
SECRET_DOC = "POLIS-88421-NE-PUBLIC"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM leisure_photos; DELETE FROM leisure_items; "
                "DELETE FROM leisure_offers; DELETE FROM leisure_providers"
            ))
        yield c


@pytest.fixture(autouse=True)
def _reset_rate():
    leisure_mod._HITS.clear()
    yield
    leisure_mod._HITS.clear()


def _base(**extra):
    data = {
        "display_name": "ДЕМО организатор, не настоящий",
        "legal_status": "self_employed",
        "legal_details": "ИНН 0000000000 демо",
        "licenses_note": "допусков нет",
        "insurance_note": f"страховка {SECRET_DOC}",
        "has_instructor": "1",
        "instructor_note": "ведёт группу, без номера аттестата",
        "contact_name": SECRET_NAME,
        "contact_phone": SECRET_PHONE,
        "contact_telegram": "@demogid19",
        "title": "ДЕМО прогулка",
        "activity_type": "excursion",
        "description": "Вымышленное описание демо-активности для проверки формы, без настоящего места и организатора.",
        "meeting_address": "Демо-поляна у вымышленного моста",
        "finish_address": "Там же, где сбор",
        "duration_text": "2 часа",
        "schedule_text": "по записи за сутки",
        "weather_terms": "в сухую погоду, при грозе не выходим",
        "price_amount": "2500",
        "price_unit": "person",
        "price_text": "2 500 ₽ с человека, демо-цена",
        "included": "сопровождение демо-гида",
        "excluded": "обед и трансфер",
        "group_min": "2",
        "group_max": "8",
        "age_text": "с 10 лет",
        "weight_limit": "до 120 кг",
        "health_limits": "без острых состояний",
        "difficulty": "easy",
        "what_to_bring": "воду и закрытую обувь",
        "provided_gear": "ничего не выдаём",
        "transfer": "none",
        "seasons": "summer",
        "languages": "ru",
        "conditions": "УСЛОВИЯ-ДЕМО: предоплата не нужна, участник в закрытой обуви.",
        "cancellation_terms": "отмена за сутки, деньги возвращает организатор",
        "equipment_state": "",
        "vest": "na",
        "helmet": "na",
        "gear_check": "снаряжение не выдаём",
        "briefing": "yes",
        "briefing_note": "коротко перед стартом",
        "consent": "1",
        "consent_own_service": "1",
        "consent_docs": "1",
    }
    data.update(extra)
    return data


def _as_lists(data):
    """Один seasons/languages в словаре TestClient всё равно отдаёт getlist."""
    return data


def _token(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def _submit(client, data, files=None):
    page = client.get("/dosug/zayavka")
    payload = _as_lists(data)
    payload["csrf"] = _token(page.text)
    return client.post("/dosug/zayavka", data=payload, files=files or {}, headers=ORIGIN, follow_redirects=False)


def _png(width, height=800, color=(39, 140, 62)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def test_fee_is_five_percent_and_lodging_fee_stays():
    assert cat.LEISURE_SERVICE_FEE_PCT == Decimal("5")
    parts = cat.fee_parts(Decimal("2500"))
    assert parts["fee"] == Decimal("125") and parts["pay_provider"] == Decimal("2375")
    assert parts["discount"] == parts["fee"] and parts["scheme"] == "from_price" and parts["public"] is False
    on_top = cat.fee_parts(Decimal("2500"), scheme="on_top")
    assert on_top["pay_provider"] == Decimal("2500") and on_top["guest_total"] == Decimal("2625") and on_top["public"] is False
    assert cat.fee_parts(Decimal("2500"), scheme="hidden")["fee"] == Decimal("0")
    assert Partner.service_fee_pct.default.arg == 5
    assert LeisureOffer.service_fee_pct.default.arg == 5


def test_leisure_copy_is_edited_in_admin_and_shown_on_the_page(client):
    from site_app import site_texts
    site_texts._REGISTRY.clear()
    info = site_texts.registry()["dosug.form.lead"]
    assert info["page"] == "dosug" and "Карточка для гостей" in info["default"]
    key = "dosug.form.lead"
    try:
        saved = client.post(
            "/admin/texts/pages/edit",
            data={"key": key, "value": "Текст досуга из админки"},
            auth=AUTH, follow_redirects=False,
        )
        assert saved.status_code == 303, saved.text
        assert "Текст досуга из админки" in client.get("/dosug/zayavka").text
    finally:
        client.post("/admin/texts/pages/edit", data={"key": key, "value": "", "action": "reset"}, auth=AUTH)
    assert "Текст досуга из админки" not in client.get("/dosug/zayavka").text
    assert "Карточка для гостей" in client.get("/dosug/zayavka").text


def test_phone_and_telegram_are_required_and_normalized():
    from site_app.leisure import normalize_telegram
    assert normalize_telegram("@Demo_Gid") == "https://t.me/Demo_Gid"
    assert normalize_telegram("t.me/Demo_Gid/") == "https://t.me/Demo_Gid"
    assert normalize_telegram("https://telegram.me/Demo_Gid") == "https://t.me/Demo_Gid"
    with pytest.raises(leisure_mod.FormError) as empty:
        normalize_telegram("")
    assert empty.value.field == "contact_telegram"
    with pytest.raises(leisure_mod.FormError):
        normalize_telegram("не ссылка")
    data = _base()
    data["seasons"] = ["summer"]
    data["languages"] = ["ru"]
    data["consent_own_service"] = True
    data["consent_docs"] = True
    data["contact_phone"] = ""
    with pytest.raises(leisure_mod.FormError) as no_phone:
        leisure_mod.validate_provider(data)
    assert no_phone.value.field == "contact_phone"


def test_form_asks_for_phone_and_telegram_and_pins_the_error(client):
    page = client.get("/dosug/zayavka").text
    assert "Укажите, пожалуйста, ваш контактный номер телефона и ссылку на Telegram. Мы свяжемся с вами для уточнения деталей." in page
    assert page.count('name="contact_phone"') == 1
    assert 'name="contact_telegram"' in page
    missing = _submit(client, _base(contact_telegram=""))
    assert missing.status_code == 400
    assert 'href="#lz-error"' in missing.text
    assert missing.text.find('name="contact_telegram"') < missing.text.find('id="lz-error"')


def test_form_lists_research_fields_and_does_not_sell(client):
    html = client.get("/dosug/zayavka").text
    assert 'name="csrf"' in html
    for name in (
        "duration_text", "included", "excluded", "group_min", "group_max", "age_text", "weight_limit",
        "health_limits", "meeting_address", "finish_address", "weather_terms", "cancellation_terms",
        "what_to_bring", "provided_gear", "vest", "helmet", "gear_check", "briefing", "equipment_state",
        "conditions", "consent_own_service", "consent_docs", "company_url",
    ):
        assert f'name="{name}"' in html, name
    assert "от 6" in html and "1200" in html and "жилетах" in html
    assert "не является агентом" in html and "не продаёт мою услугу" in html
    assert "аттестат" in html and "лицензию на перевозку" in html
    low = html.lower()
    assert "мы прода" not in low and "мы организ" not in low
    assert "турпродукт" not in low
    assert 'name="robots" content="noindex, nofollow"' in html
    assert "Канатная дорога" in html and "data-cat=\"rafting\"" in html and "data-cat=\"cable\"" in html


def test_category_rules_reject_incomplete_answers():
    ok = _base()
    ok["seasons"] = ["summer"]
    ok["languages"] = ["ru"]
    ok["consent_own_service"] = True
    ok["consent_docs"] = True
    validate_offer(ok)

    broken = dict(ok)
    broken["group_max"] = ""
    with pytest.raises(leisure_mod.FormError):
        validate_offer(broken)

    raft = dict(ok, activity_type="rafting", vest="yes", equipment_state="лодки осмотрены весной, демо")
    with pytest.raises(leisure_mod.FormError):
        validate_offer(raft)
    raft.update({
        "extra_rafting_flood_cancel": "при паводке выше метки не выходим",
        "extra_rafting_vest_for_all": "жилет каждому",
        "extra_rafting_water_briefing": "на берегу десять минут",
    })
    assert validate_offer(raft)["category_extra"]["flood_cancel"].startswith("при паводке")
    raft["vest"] = "na"
    with pytest.raises(leisure_mod.FormError):
        validate_offer(raft)

    horse = dict(ok, activity_type="horse")
    with pytest.raises(leisure_mod.FormError):
        validate_offer(horse)
    horse["extra_horse_age"] = "с 7 лет со взрослым"
    horse["extra_horse_weight"] = "до 100 кг"
    assert validate_offer(horse)["category_extra"]["weight"] == "до 100 кг"

    jeep = dict(ok, activity_type="jeeping", equipment_state="УАЗ 2018, демо, без рекламы")
    jeep["extra_jeeping_driving_license"] = "за рулём водитель организатора"
    with pytest.raises(leisure_mod.FormError):
        validate_offer(jeep)
    jeep["extra_jeeping_passenger_license"] = "LIC-773199"
    cleaned = validate_offer(jeep)
    assert cleaned["category_extra"]["passenger_license"] == "LIC-773199"
    public = cat.public_extra("jeeping", cleaned["category_extra"])
    assert public[0][0].startswith("Какие права")
    assert all("LIC-773199" not in text for _label, text in public)

    hike = dict(ok, activity_type="hike", extra_hike_permit_needed="yes")
    with pytest.raises(leisure_mod.FormError):
        validate_offer(hike)
    hike["extra_hike_permit_note"] = "пропуск оформляют на КПП, номер сюда не пишем"
    assert validate_offer(hike)["category_extra"]["permit_needed"] == "yes"

    cable = dict(ok, activity_type="cable")
    with pytest.raises(leisure_mod.FormError):
        validate_offer(cable)
    cable["extra_cable_cable_rules"] = "рост от 125 см, дети со взрослым"
    cable["extra_cable_cable_weather"] = "при ветре дорога стоит"
    assert "cable_weather" in validate_offer(cable)["category_extra"]


def test_narrow_photo_is_rejected_and_wide_one_is_kept():
    with pytest.raises(PhotoError):
        prepare_image(_png(800))
    wide, _thumb = prepare_image(_png(MIN_WIDTH))
    assert wide[:4] == b"RIFF"


def test_post_requires_origin_csrf_and_rate_limit(client, monkeypatch):
    open_page = client.get("/dosug/zayavka")
    token = _token(open_page.text)
    no_origin = client.post("/dosug/zayavka", data={**_base(title="без origin"), "csrf": token})
    assert no_origin.status_code == 403
    evil = client.post(
        "/dosug/zayavka", data={**_base(title="чужой сайт"), "csrf": token},
        headers={"Origin": "https://evil.example"},
    )
    assert evil.status_code == 403
    fresh = TestClient(app)
    missing = fresh.post("/dosug/zayavka", data={**_base(), "csrf": "нет-такого"}, headers=ORIGIN)
    assert missing.status_code == 403

    monkeypatch.setattr(leisure_mod, "RATE_MAX", 2)
    leisure_mod._HITS.clear()
    assert _submit(client, _base(title=f"лимит {uuid.uuid4().hex[:4]}")).status_code == 303
    assert _submit(client, _base(title=f"лимит {uuid.uuid4().hex[:4]}")).status_code == 303
    assert _submit(client, _base(title=f"лимит {uuid.uuid4().hex[:4]}")).status_code == 429


def test_honeypot_and_missing_field_do_not_publish(client):
    before = engine.connect().execute(text("SELECT count(*) FROM leisure_offers")).scalar()
    trapped = _submit(client, _base(title="бот заполнил ловушку", company_url="http://spam.test"))
    assert trapped.status_code == 303 and "sent=bot" in trapped.headers["location"]
    missing = _submit(client, _base(title="без отмены", cancellation_terms=""))
    assert missing.status_code == 400 and "Отмена" in missing.text
    assert 'id="lz-error"' in missing.text and 'href="#lz-error"' in missing.text
    assert missing.text.find('name="cancellation_terms"') < missing.text.find('id="lz-error"') < missing.text.find('name="equipment_state"')
    after = engine.connect().execute(text("SELECT count(*) FROM leisure_offers WHERE title LIKE 'без отмены%' OR title LIKE 'бот заполнил%'")).scalar()
    assert after == 0
    assert engine.connect().execute(text("SELECT count(*) FROM leisure_offers")).scalar() >= before


def test_submit_moderate_slug_fee_and_hide_documents(client, monkeypatch):
    uid = uuid.uuid4().hex[:6]
    title = f"ДЕМО прогулка {uid}"
    sent = _submit(client, _base(title=title))
    assert sent.status_code == 303, sent.text
    code = sent.headers["location"].rstrip("/").split("/")[-1].split("?")[0]
    assert client.get(f"/dosug/kabinet/{code}").status_code == 200
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, slug, status, is_published, service_fee_pct FROM leisure_offers WHERE title=:t"), {"t": title}).one()
    assert row.status == "pending" and row.is_published is False and Decimal(row.service_fee_pct) == Decimal("5")
    assert client.get(f"/dosug/{row.slug}").status_code == 404
    assert client.get(f"/dosug/{row.id}").status_code == 404
    sitemap = client.get("/sitemap.xml").text
    assert f"/dosug/{row.slug}" not in sitemap and f"/dosug/{row.id}" not in sitemap
    assert "/dosug/zayavka" not in sitemap

    admin = client.get(f"/admin/dosug/{row.id}", auth=AUTH)
    assert admin.status_code == 200 and "Условия" in admin.text and "Состояние" in admin.text
    assert SECRET_PHONE in admin.text and SECRET_DOC in admin.text
    assert 'href="https://t.me/demogid19"' in admin.text
    saved = client.post(
        f"/admin/dosug/{row.id}",
        data={**_base(title=title + " правка"), "csrf": _token(admin.text), "action": "approve", "service_fee_pct": "5"},
        headers=ORIGIN, auth=AUTH, follow_redirects=False,
    )
    assert saved.status_code == 303, saved.text
    with engine.connect() as conn:
        published = conn.execute(text("SELECT slug, status, is_published, conditions FROM leisure_offers WHERE id=:i"), {"i": row.id}).one()
    assert published.status == "approved" and published.is_published is True
    assert published.conditions.startswith("УСЛОВИЯ-ДЕМО")
    page = client.get(f"/dosug/{published.slug}")
    assert page.status_code == 200
    html = page.text
    assert f'<link rel="canonical" href="{SITE_URL}/dosug/{published.slug}">' in html
    assert "УСЛОВИЯ-ДЕМО" in html.split('id="usloviya"')[1].split('id="snaryazhenie"')[0]
    assert "УСЛОВИЯ-ДЕМО" not in html.split('id="opisanie"')[1].split('id="usloviya"')[0]
    assert "125 ₽" not in html and "2 375" not in html and "скидк" not in html.lower()
    admin_html = client.get(f"/admin/dosug/{row.id}", auth=AUTH).text
    assert "from_price" in admin_html and "125 ₽" in admin_html and "скидк" not in admin_html.lower()
    assert SECRET_PHONE not in html and SECRET_NAME not in html and SECRET_DOC not in html
    assert "t.me/demogid19" not in html and "demogid19" not in html
    assert "не агент и не продаёт" in html
    by_id = client.get(f"/dosug/{row.id}", follow_redirects=False)
    assert by_id.status_code == 301 and by_id.headers["location"] == f"/dosug/{published.slug}"
    locs = [e.text for e in ElementTree.fromstring(client.get("/sitemap.xml").text).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert SITE_URL + f"/dosug/{published.slug}" in locs
    assert not any(re.search(r"/dosug/\d+$", loc) for loc in locs)

    renamed = f"demo-extra-{uid}"
    again = client.get(f"/admin/dosug/{row.id}", auth=AUTH)
    renamed_post = client.post(
        f"/admin/dosug/{row.id}",
        data={**_base(title=title + " правка"), "csrf": _token(again.text), "action": "save", "slug": renamed, "service_fee_pct": "5"},
        headers=ORIGIN, auth=AUTH, follow_redirects=False,
    )
    assert renamed_post.status_code == 303, renamed_post.text
    old = client.get(f"/dosug/{published.slug}", follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"/dosug/{renamed}"
    assert client.get(f"/dosug/{row.id}", follow_redirects=False).headers["location"] == f"/dosug/{renamed}"
    with engine.connect() as conn:
        stored = conn.execute(text(
            "SELECT old_slug, entity_id FROM slug_redirects WHERE kind='leisure' AND old_slug=:s"
        ), {"s": published.slug}).one()
    assert stored.entity_id == row.id
    monkeypatch.setattr(cat, "LEISURE_FEE_SCHEME", "from_price_public")
    shown = client.get(f"/dosug/{renamed}").text
    assert "125 ₽" in shown and "скидк" not in shown.lower()
    monkeypatch.setattr(cat, "LEISURE_FEE_SCHEME", "from_price")
    rejected = client.post(
        f"/admin/dosug/{row.id}",
        data={**_base(title=title + " правка"), "csrf": _token(client.get(f"/admin/dosug/{row.id}", auth=AUTH).text),
              "action": "reject", "slug": renamed, "service_fee_pct": "5"},
        headers=ORIGIN, auth=AUTH, follow_redirects=False,
    )
    assert rejected.status_code == 303, rejected.text
    assert client.get(f"/dosug/{row.id}", follow_redirects=False).status_code == 404
    assert client.get(f"/dosug/{renamed}", follow_redirects=False).status_code == 404


def test_photo_alt_and_repeat_supply_stay_hidden_until_approved(client):
    uid = uuid.uuid4().hex[:6]
    title = f"ДЕМО сплав {uid}"
    payload = _base(
        title=title, activity_type="rafting", vest="yes",
        equipment_state="СОСТОЯНИЕ-ДЕМО: лодки 2024 года, без повреждений корпуса.",
        extra_rafting_flood_cancel="при паводке выше метки не выходим",
        extra_rafting_vest_for_all="жилет каждому, включая детей",
        extra_rafting_water_briefing="инструктор на берегу",
        photos_honest="1", photos_vests="1",
    )
    bare = _submit(client, payload, files={"photo_1": ("demo.png", _png(MIN_WIDTH), "image/png")})
    assert bare.status_code == 400 and "подпись" in bare.text.lower()
    payload_alt = dict(payload)
    files = {"photo_1": ("demo.png", _png(MIN_WIDTH), "image/png")}
    page = client.get("/dosug/zayavka")
    payload_alt["csrf"] = _token(page.text)
    payload_alt["alt_1"] = "ДЕМО кадр: люди в жилетах на спокойной воде"
    sent = client.post("/dosug/zayavka", data=payload_alt, files=files, headers=ORIGIN, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    narrow = dict(payload_alt)
    page = client.get("/dosug/zayavka")
    narrow["csrf"] = _token(page.text)
    narrow["title"] = title + " узкое"
    bad = client.post(
        "/dosug/zayavka", data=narrow,
        files={"photo_1": ("small.png", _png(600), "image/png")},
        headers=ORIGIN, follow_redirects=False,
    )
    assert bad.status_code == 400 and "1200" in bad.text

    code = sent.headers["location"].rstrip("/").split("/")[-1].split("?")[0]
    with engine.connect() as conn:
        offer_id, slug = conn.execute(text("SELECT id, slug FROM leisure_offers WHERE title=:t"), {"t": title}).one()
    admin = client.get(f"/admin/dosug/{offer_id}", auth=AUTH)
    data = {**payload, "csrf": _token(admin.text), "action": "approve", "service_fee_pct": "5"}
    for match in re.finditer(r'name="(alt_id_\d+)" value="([^"]*)"', admin.text):
        data[match.group(1)] = match.group(2)
    approved = client.post(f"/admin/dosug/{offer_id}", data=data, headers=ORIGIN, auth=AUTH, follow_redirects=False)
    assert approved.status_code == 303, approved.text
    html = client.get(f"/dosug/{slug}").text
    assert 'alt="ДЕМО кадр: люди в жилетах на спокойной воде"' in html or "ДЕМО кадр" in html
    state = html.split('id="sostoyanie"')[1]
    assert "СОСТОЯНИЕ-ДЕМО" in state
    assert "СОСТОЯНИЕ-ДЕМО" not in html.split('id="opisanie"')[1].split('id="usloviya"')[0]
    assert "при паводке" in html
    assert SECRET_DOC not in html

    item_page = client.get(f"/dosug/zayavka?code={code}&offer={offer_id}")
    item = client.post(
        "/dosug/zayavka",
        data={
            "csrf": _token(item_page.text), "code": code, "mode": "item", "offer_id": str(offer_id),
            "item_title": "Новая поставка демо-жилетов", "item_state": "ПОСТАВКА-ДЕМО: новые жилеты, не ношены",
            "item_quantity": "4",
        },
        headers=ORIGIN, follow_redirects=False,
    )
    assert item.status_code == 303
    public = client.get(f"/dosug/{slug}").text
    assert "ПОСТАВКА-ДЕМО" not in public
    cabinet = client.get(f"/dosug/kabinet/{code}").text
    assert "Новая поставка демо-жилетов" in cabinet and "На модерации" in cabinet
