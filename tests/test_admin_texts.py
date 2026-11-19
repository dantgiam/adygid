"""Админка «Тексты сайта»: факты «Коротко для поездки» в базе, плашки,
тексты страниц, история, кэш и безопасность разметки."""
import json
import os
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import engine
from app.main import app
from site_app import seo, site_texts, travel_notices as tn, trip_facts
from site_app.admin_texts_db import ensure_admin_text_tables

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
URL = "https://x.test/mesta/1"


@pytest.fixture()
def client():
    return TestClient(app)


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def _place(client, name, minutes=None):
    r = client.post("/api/checkpoints", json={"name": name, "lon": 40.1, "lat": 44.1, "is_paid": False}, auth=AUTH)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if minutes:
        assert client.patch(f"/api/checkpoints/{pid}", json={"duration_minutes": minutes}, auth=AUTH).status_code == 200
    return pid


# ───────── перенос из кода: снаружи ничего не меняется ─────────

@pytest.mark.parametrize("pid", trip_facts.code_place_ids())
def test_block_from_code_reproduces_seo_output(pid):
    b = trip_facts.block_from_code(pid)
    name, district = "Название", "khadzhokh"
    legacy = seo.place_facts(pid)
    f = trip_facts.facts(b, name)
    if legacy is None:
        assert f is None
    else:
        assert f == {k: v for k, v in legacy.items() if k != "seo_title"}
    assert trip_facts.checked(b) == seo.practical_checked(pid)
    assert trip_facts.title(b, name, district) == seo.place_title(name, district, pid)
    assert trip_facts.description(b, name) == seo.fact_description(pid, name)
    assert trip_facts.heading(b, name) == seo.practical_heading(pid, name)
    kw = dict(name=name, url=URL, description="d", images=["i"], lat=44.0, lon=40.0, is_paid=True)
    assert seo.place_ld(pid, **kw, facts=f, checked=trip_facts.checked(b)) == seo.place_ld(pid, **kw)


def test_seed_is_idempotent_and_keeps_admin_edits():
    ensure_admin_text_tables()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT count(*) FROM place_trip_blocks")).scalar()
        assert n >= len(trip_facts.code_place_ids())
        conn.execute(text("UPDATE place_trip_blocks SET seo_title = 'Правка админа' WHERE place_id = 55"))
    stats = ensure_admin_text_tables()
    assert stats == {"blocks": 0, "notices": 0}
    with engine.begin() as conn:
        assert conn.execute(text("SELECT seo_title FROM place_trip_blocks WHERE place_id = 55")).scalar() == "Правка админа"
        conn.execute(text("UPDATE place_trip_blocks SET seo_title = NULL WHERE place_id = 55"))
    trip_facts.invalidate()
    assert trip_facts.block_for(55)["seo_title"] == ""


def test_db_block_wins_over_code_and_missing_falls_back():
    trip_facts.invalidate()
    assert trip_facts.block_for(55)["from_code"] is False
    assert trip_facts.block_for(999999) is None
    assert trip_facts.block_for(29)["rows"]


# ───────── редактор карточки ─────────

def _form(**extra):
    base = {
        "enabled": "1", "auto_visit": "1", "heading_name": "Тестовый водопад",
        "seo_title": "", "seo_description": "", "combine_ids": "", "route_id": "",
        "sources": "официальный сайт | https://example.org/hours",
        "sf_locality": "пос. Тестовый", "sf_street": "", "sf_phone": "+7 900 000-00-00",
        "r0_key": "hours", "r0_label": "Часы работы", "r0_text": "Ежедневно 9:00–18:00.",
        "r0_verified": "1", "r0_checked_on": "2026-11-18", "r0_ld_short": "ежедневно 9:00–18:00",
        "r0_ld_opens": "09:00", "r0_ld_closes": "18:00", "r0_order": "0",
        "r1_key": "tickets", "r1_label": "Вход", "r1_text": "300 ₽, дети бесплатно.",
        "r1_ld_price": "300", "r1_ld_label": "300 ₽, дети бесплатно", "r1_ld_place": "Вход к водопаду", "r1_order": "1",
        "r2_key": "custom", "r2_label": "Парковка", "r2_text": "Платная, 100 ₽.", "r2_order": "2",
        "r2_source_url": "https://example.org/parking",
    }
    for d in range(7):
        base[f"r0_ld_day_{['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][d]}"] = "1"
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


def test_editor_saves_rows_and_ld_uses_only_verified(client):
    pid = _place(client, "Тестовый водопад для редактора", minutes=60)
    r = client.get(f"/admin/texts/places/{pid}", auth=AUTH)
    assert r.status_code == 200 and "пока из кода" in r.text and "Так примерно будет в выдаче" in r.text
    r = client.post(f"/admin/texts/places/{pid}", data=_form(), auth=AUTH, follow_redirects=False)
    assert r.status_code == 303, r.text
    html = client.get(f"/mesta/{pid}").text
    assert '<th scope="row">Парковка</th>' in html and 'class="practical-row practical-custom"' in html
    assert 'href="https://example.org/parking"' in html and "источник</a>" in html
    # Время посещения из длительности встало после «Входа», до своей строки
    assert html.index(">Вход</th>") < html.index("Время посещения") < html.index(">Парковка</th>")
    assert "<title>Тестовый водопад: время работы 2026 и как добраться</title>" in html
    assert '<time datetime="2026-11-18">18 ноября 2026</time>' in html
    attr = next(b for b in _ld_blocks(html) if b.get("@type") == "TouristAttraction")
    assert attr["openingHoursSpecification"][0]["opens"] == "09:00"
    assert attr["telephone"] == "+7 900 000-00-00"
    # Цена не отмечена «проверено» — ни Offer, ни isAccessibleForFree из неё
    assert "Offer" not in [b.get("@type") for b in _ld_blocks(html)]
    # Отметили цену — появился Offer, заголовок и description с ценой
    r = client.post(f"/admin/texts/places/{pid}", data=_form(r1_verified="1", r1_checked_on="2026-11-19"), auth=AUTH, follow_redirects=False)
    html = client.get(f"/mesta/{pid}").text
    offer = next(b for b in _ld_blocks(html) if b.get("@type") == "Offer")
    assert offer["price"] == 300 and offer["url"] == "https://example.org/hours"
    assert "цена входа 2026" in html and '<time datetime="2026-11-19">' in html
    m = re.search(r'<meta name="description" content="([^"]+)"', html)
    assert "Вход — 300 ₽, дети бесплатно." in m.group(1)
    # Ручной title и description побеждают автоматические
    client.post(f"/admin/texts/places/{pid}", data=_form(seo_title="Мой title", seo_description="Моё описание"), auth=AUTH)
    html = client.get(f"/mesta/{pid}").text
    assert "<title>Мой title</title>" in html and 'content="Моё описание"' in html
    # Сняли «проверено» со всех строк — фактов в разметке нет
    form = _form(r0_verified=None)
    client.post(f"/admin/texts/places/{pid}", data=form, auth=AUTH)
    html = client.get(f"/mesta/{pid}").text
    attr = next(b for b in _ld_blocks(html) if b.get("@type") == "TouristAttraction")
    assert "openingHoursSpecification" not in attr and "telephone" not in attr
    assert "Цены и часы меняются" in html
    # История: три сохранения, можно вернуть версию
    with engine.connect() as conn:
        hist = conn.execute(text("SELECT id, author FROM admin_text_history WHERE entity='place' AND entity_key=:k ORDER BY id"), {"k": str(pid)}).all()
    assert len(hist) == 4 and hist[0][1] == AUTH[0]
    r = client.post(f"/admin/texts/history/{hist[1][0]}/restore", auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    assert "Offer" in [b.get("@type") for b in _ld_blocks(client.get(f"/mesta/{pid}").text)]
    # Скрыть блок
    client.post(f"/admin/texts/places/{pid}", data=_form(enabled=None), auth=AUTH)
    assert 'id="kratko"' not in client.get(f"/mesta/{pid}").text


def test_editor_validates_input(client):
    pid = _place(client, "Тестовое место для проверки ввода")
    bad = [
        _form(r0_ld_opens="9 утра"),
        _form(r1_ld_price="триста"),
        _form(r2_source_url="javascript:alert(1)"),
        _form(sources="плохой | ftp://x"),
        _form(r0_ld_spec="Пн-Пт весь день"),
    ]
    for data in bad:
        assert client.post(f"/admin/texts/places/{pid}", data=data, auth=AUTH).status_code == 400
    # Сложное расписание по-русски
    r = client.post(f"/admin/texts/places/{pid}", data=_form(r0_ld_spec="Вт Ср Чт 10:00–18:00\nСб, Вс 11:00-17:00"), auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    attr = next(b for b in _ld_blocks(client.get(f"/mesta/{pid}").text) if b.get("@type") == "TouristAttraction")
    spec = attr["openingHoursSpecification"]
    assert len(spec) == 2 and spec[1]["dayOfWeek"] == ["https://schema.org/Saturday", "https://schema.org/Sunday"]


def test_text_in_row_is_escaped(client):
    pid = _place(client, "Тестовое место для экранирования")
    client.post(f"/admin/texts/places/{pid}", data=_form(r2_text='<img src=x onerror=alert(1)>'), auth=AUTH)
    html = client.get(f"/mesta/{pid}").text
    assert "<img src=x onerror" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html


def test_admin_requires_login_and_same_origin(client):
    assert client.get("/admin/texts/places").status_code == 401
    assert client.get("/admin/texts/pages", auth=("admin", "wrong")).status_code == 401
    pid = _place(client, "Тестовое место для origin")
    r = client.post(f"/admin/texts/places/{pid}", data=_form(), auth=AUTH, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/admin/texts/pages/edit", data={"key": "home.hero.cta_main", "value": "x"}, auth=AUTH,
                    headers={"Referer": "https://evil.example/page"})
    assert r.status_code == 403


def test_places_list_page(client):
    r = client.get("/admin/texts/places", auth=AUTH)
    assert r.status_code == 200 and "Коротко для поездки" in r.text and "На сайте ↗" in r.text


# ───────── тексты страниц ─────────

def test_registry_finds_template_texts():
    reg = site_texts.registry()
    assert len(reg) >= 100
    assert reg["home.hero.cta_main"]["default"] == "Куда вы едете?" and reg["home.hero.cta_main"]["url"] == "/"
    assert reg["podbor.meta.title"]["plain"] is True
    assert reg["home.widget.title_end"]["default"] == " прямо на&nbsp;сайте?"
    pages = {i["page"] for i in reg.values()}
    assert {"home", "podbor", "partners", "v", "nav", "footer", "places"} <= pages


def test_render_inline_allows_only_safe_markup():
    out = str(site_texts.render_inline('**Жир** и *курсив* [места](/mesta) [сайт](https://ya.ru/?a=1&b=2) '
                                       '[зло](javascript:alert(1)) <script>x</script> "кавычки"\nвторая'))
    assert "<strong>Жир</strong>" in out and "<em>курсив</em>" in out
    assert '<a href="/mesta">места</a>' in out
    assert '<a href="https://ya.ru/?a=1&amp;b=2" target="_blank" rel="noopener">сайт</a>' in out
    assert "javascript:" not in out.replace("[зло](javascript:alert(1))", "") and "<script>" not in out
    assert "&lt;script&gt;" in out and "<br>вторая" in out
    assert "href=\"javascript" not in out
    assert site_texts.render_plain("[ссылка](/x) **жир**  и\nперенос") == "ссылка жир и перенос"


def test_page_text_edit_is_visible_at_once_and_resets(client):
    key = "home.hero.cta_main"
    before = client.get("/").text
    assert ">Куда вы едете?</a>" in before
    r = client.get(f"/admin/texts/pages/edit?key={key}", auth=AUTH)
    assert r.status_code == 200 and "открыть на сайте" in r.text
    try:
        r = client.post("/admin/texts/pages/edit", data={"key": key, "value": "Куда **едем**? <b>x</b>"}, auth=AUTH, follow_redirects=False)
        assert r.status_code == 303
        html = client.get("/").text
        assert ">Куда <strong>едем</strong>? &lt;b&gt;x&lt;/b&gt;</a>" in html
        # tp: в <title> без разметки
        client.post("/admin/texts/pages/edit", data={"key": "home.meta.title", "value": "Главная **АдыГид** <x>"}, auth=AUTH)
        assert "<title>Главная АдыГид &lt;x&gt;</title>" in client.get("/").text
        lst = client.get("/admin/texts/pages?q=едем", auth=AUTH).text
        assert key in lst and "изменено" in lst
        assert client.post("/admin/texts/pages/edit", data={"key": "nope.key", "value": "x"}, auth=AUTH).status_code == 404
        assert client.post("/admin/texts/pages/edit", data={"key": key, "value": "x" * 5000}, auth=AUTH).status_code == 400
    finally:
        client.post("/admin/texts/pages/edit", data={"key": key, "value": "", "action": "reset"}, auth=AUTH)
        client.post("/admin/texts/pages/edit", data={"key": "home.meta.title", "value": "", "action": "reset"}, auth=AUTH)
    assert client.get("/").text.count(">Куда вы едете?</a>") == before.count(">Куда вы едете?</a>")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM site_texts WHERE key = :k"), {"k": key}).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM admin_text_history WHERE entity='text' AND entity_key=:k"), {"k": key}).scalar() >= 2


# ───────── плашки ─────────

@pytest.fixture()
def notice_backup():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM site_notices")).mappings().all()
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM site_notices"))
        for r in rows:
            cols = ", ".join(r.keys())
            conn.execute(text(f"INSERT INTO site_notices ({cols}) VALUES ({', '.join(':' + k for k in r.keys())})"), dict(r))
    tn.invalidate()


def test_seeded_notice_matches_code_notice():
    tn.invalidate()
    for d in (date(2026, 11, 19), date(2026, 12, 25), date(2027, 1, 3), date(2026, 12, 31), date(2027, 3, 1), date(2027, 11, 20)):
        got = tn.current_notice("podbor", d)
        if got:
            assert got.pop("slug") == "novogodnie-kanikuly"
        assert got == tn.holiday_notice(d)


def test_notice_windows_wrap_new_year():
    n = {"repeat_yearly": True, "winter_from": date(2026, 11, 15), "show_from": date(2026, 12, 20), "show_to": date(2027, 1, 8)}
    assert tn.notice_windows(n, date(2030, 1, 5)) == (True, False)
    assert tn.notice_windows(n, date(2030, 12, 1)) == (False, True)
    assert tn.notice_windows(n, date(2030, 2, 1)) == (False, False)
    assert tn.notice_windows(dict(n, repeat_yearly=False), date(2030, 1, 5)) == (False, False)
    assert tn.notice_windows({}, date(2030, 1, 5)) == (True, False)


def test_notice_editor_changes_podbor(client, monkeypatch, notice_backup):
    monkeypatch.setattr(tn, "today_msk", lambda now=None: date(2026, 12, 25))
    page = client.get("/admin/texts/notices", auth=AUTH)
    assert page.status_code == 200 and "Новогодние каникулы" in page.text
    nid = re.search(r'href="/admin/texts/notices/(\d+)"', page.text).group(1)
    assert "Совет от местных" in client.get(f"/admin/texts/notices/{nid}", auth=AUTH).text
    data = {"id": nid, "name": "Новогодние каникулы", "is_enabled": "1", "priority": "10", "repeat_yearly": "1",
            "winter_from": "2026-11-15", "show_from": "2026-12-20", "show_to": "2027-01-08",
            "kicker": "Едете на каникулы?", "kicker_late": "", "kicker_late_from": "", "title": "Свой заголовок",
            "mode": "custom", "body": "Вход {цена:55} ₽, [КПП](/mesta/55#kratko) <i>x</i>", "action": "save"}
    assert client.post("/admin/texts/notices/save", data=data, auth=AUTH, follow_redirects=False).status_code == 303
    html = client.get("/podbor").text
    assert "Свой заголовок" in html and "Едете на каникулы?" in html
    assert f'Вход {seo.place_facts(55)["price"]} ₽, <a href="/mesta/55#kratko">КПП</a> &lt;i&gt;x&lt;/i&gt;' in html
    # выключили — плашки нет
    client.post("/admin/texts/notices/save", data=dict(data, is_enabled=""), auth=AUTH)
    assert 'id="trip-notice"' not in client.get("/podbor").text
    # ошибки ввода
    assert client.post("/admin/texts/notices/save", data=dict(data, show_to=""), auth=AUTH).status_code == 400
    assert client.post("/admin/texts/notices/save", data=dict(data, mode="custom", body=""), auth=AUTH).status_code == 400
    # новая плашка с большим приоритетом и без дат — видна всем всегда
    new = dict(data, id="", name="Майские", priority="50", winter_from="", show_from="", show_to="",
               title="Майские праздники", body="Берите **дождевик**", is_enabled="1")
    r = client.post("/admin/texts/notices/save", data=new, auth=AUTH, follow_redirects=False)
    assert r.status_code == 303
    html = client.get("/podbor").text
    assert "Майские праздники" in html and "<strong>дождевик</strong>" in html and 'data-always="1"' in html
    new_id = r.headers["location"].rsplit("/", 1)[1].split("?")[0]
    client.post("/admin/texts/notices/save", data={"id": new_id, "action": "delete"}, auth=AUTH)
    assert "Майские праздники" not in client.get("/podbor").text
    assert client.get("/admin/texts/history", auth=AUTH).status_code == 200


def test_notice_seed_once_even_after_delete(notice_backup):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM site_notices"))
    ensure_admin_text_tables()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM site_notices")).scalar() == 0
    tn.invalidate()
    # Все плашки удалили в админке — на сайте плашки нет (из кода не возвращается)
    assert tn.current_notice("podbor", date(2026, 12, 25)) is None
    # А если таблица недоступна — работает плашка из кода
    tn._CACHE.update(rows=None, at=__import__("time").monotonic())
    assert tn.current_notice("podbor", date(2026, 12, 25))["title"] == "Совет от местных"
    tn.invalidate()
