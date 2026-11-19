"""«Коротко для поездки» под поиск: таблица высоко в HTML, заголовок
фразой запроса, title/description из проверенных фактов, JSON-LD
TouristAttraction (+ Offer) и одна строка «проверено · источники»."""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


@pytest.fixture()
def client():
    return TestClient(app)


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def _place(client, name):
    r = client.post("/api/checkpoints", json={"name": name, "lon": 40.136, "lat": 44.0, "is_paid": False}, auth=AUTH)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_facts_only_with_official_source_and_date():
    for pid, cfg in seo.PLACE_PRACTICAL.items():
        f = cfg.get("facts")
        if not f:
            assert "checked" not in cfg and "sources" not in cfg, pid
            continue
        assert cfg["checked"] == "2026-11-19" and cfg["sources"], pid
        assert all(k in seo.FACT_SOURCES for k in cfg["sources"]), pid
        assert f.get("hours") and cfg.get("hours"), pid
        if f.get("price") is not None:
            assert f.get("price_label") and "₽" in cfg["tickets"], pid
            assert str(f["price"]) in cfg["tickets"].replace("\u00a0", "").replace(" ", ""), pid
        if f.get("opens"):
            assert re.fullmatch(r"\d\d:\d\d", f["opens"]) and re.fullmatch(r"\d\d:\d\d", f["closes"]), pid
        for spec in f.get("hours_spec", []):
            assert set(spec["days"]) <= DAYS


def test_no_caveat_sheets_in_fields():
    """Оговорки «официально не перепроверено», «даты обновления нет» и т. п.
    больше не повторяются в каждом поле — источник и дата один раз под таблицей."""
    bad = ("не перепровер", "даты обновления", "проверено 19.11", "так написано на официальной", "на портале pokolenie")
    for pid, cfg in seo.PLACE_PRACTICAL.items():
        for key, _ in seo.PRACTICAL_LABELS:
            v = cfg.get(key)
            text = v["text"] if isinstance(v, dict) else (v if isinstance(v, str) else "")
            for b in bad:
                assert b not in text.lower(), (pid, key, b)


def test_ekocentr_fee_is_from_news_not_order_359():
    for pid in (62, 63):
        cfg = seo.PLACE_PRACTICAL[pid]
        assert "359" not in cfg["tickets"]
        assert "zapoved_news" in cfg["sources"] and "zapoved_order" not in cfg["sources"]


def test_lago_cash_and_price_consistent():
    f = seo.place_facts(55)
    assert f["cash_only"] is True and f["price"] == seo.ZAPOVED_PRICE == 500
    assert "Только наличные" in seo.PLACE_PRACTICAL[55]["cash"]
    assert seo.place_facts(56)["opens"] == f["opens"] == "05:00"


def test_titles_and_descriptions_from_facts():
    assert seo.place_title("Плато Лаго-Наки", "lagonaki", 55) == "Плато Лаго-Наки: время работы, цена входа 2026, как добраться"
    assert seo.place_title("Хаджохская теснина", "khadzhokh", 24) == "Хаджохская теснина: время работы 2026 и как добраться"
    d = seo.fact_description(55, "Плато Лаго-Наки")
    assert "05:00–20:00" in d and "500 ₽" in d and "только наличные" in d and "19.11.2026" in d
    for pid in seo.PLACE_PRACTICAL:
        t = seo.fact_title(pid, "x")
        if t:
            assert "₽" not in t and len(t) <= 80, t
            desc = seo.fact_description(pid, "x")
            assert 60 <= len(desc) <= 230, (pid, len(desc), desc)


def test_place_ld_shape_is_schema_valid():
    url = "https://www.adygid.ru/mesta/55"
    blocks = seo.place_ld(55, name="Плато Лаго-Наки", url=url, description="d", images=[], lat=44.08, lon=40.01)
    attr, offer = blocks
    assert attr["@type"] == "TouristAttraction" and attr["@id"] == url + "#place"
    assert attr["geo"]["latitude"] == 44.08 and attr["publicAccess"] is True
    assert attr["isAccessibleForFree"] is False
    spec = attr["openingHoursSpecification"][0]
    assert spec["opens"] == "05:00" and spec["closes"] == "20:00" and len(spec["dayOfWeek"]) == 7
    assert attr["mainEntityOfPage"]["dateModified"] == "2026-11-19"
    names = {f["name"]: f["value"] for f in attr["amenityFeature"]}
    assert names == {"Оплата только наличными": True, "Можно с домашними животными": False}
    # свойств, которых нет у Place в schema.org, в TouristAttraction не пишем
    assert not {"offers", "petsAllowed", "priceRange", "paymentAccepted"} & set(attr)
    assert offer["@type"] == "Offer" and offer["price"] == 500 and offer["priceCurrency"] == "RUB"
    assert offer["availableAtOrFrom"] == {"@id": url + "#place"}
    assert offer["acceptedPaymentMethod"] == "https://schema.org/Cash"
    # без фактов — прежняя простая разметка, без часов и цены
    plain = seo.place_ld(52, name="Гранитный каньон", url="u", description="d", images=[], lat=None, lon=None)
    assert len(plain) == 1 and "openingHoursSpecification" not in plain[0] and "isAccessibleForFree" not in plain[0]
    # музей Востока — два интервала по дням недели
    vostok = seo.place_ld(76, name="m", url="u", description="d", images=[], lat=1, lon=2)[0]
    assert len(vostok["openingHoursSpecification"]) == 2 and "Monday" not in json.dumps(vostok)


def test_card_renders_table_high_with_heading_and_ld(client, monkeypatch):
    pid = _place(client, "Тестовый экоцентр")
    monkeypatch.setitem(seo.PLACE_PRACTICAL, pid, dict(seo.PLACE_PRACTICAL[62], combine=[]))
    html = client.get(f"/mesta/{pid}").text
    assert "<title>Музей природы в Гузерипле: время работы, цена входа 2026, как добраться</title>" in html
    m = re.search(r'<meta name="description" content="([^"]+)"', html)
    assert m and "10:00–17:00" in m.group(1) and "500 ₽" in m.group(1)
    assert '<h2 class="practical-title" id="practical-title">Музей природы в Гузерипле: время работы и цена входа</h2>' in html
    assert '<table class="practical-table">' in html and '<th scope="row">Часы работы</th>' in html
    # часы — первая строка, блок — до описания
    assert html.index('<th scope="row">Часы работы</th>') < html.index('<th scope="row">Вход</th>')
    assert html.index('id="practical-title"') < html.index('class="like-row"')
    assert '<time datetime="2026-11-19">19 ноября 2026</time>' in html
    assert html.count("rezhim-raboty") >= 1 and "источник</a>" not in html
    types = [b.get("@type") for b in _ld_blocks(html)]
    assert "TouristAttraction" in types and "Offer" in types
    attr = next(b for b in _ld_blocks(html) if b.get("@type") == "TouristAttraction")
    assert attr["openingHoursSpecification"][0]["opens"] == "10:00"
    assert attr["address"]["streetAddress"] == "ул. Заречная, 5"
    assert attr["url"].endswith(client.get(f"/mesta/{pid}", follow_redirects=False).headers["location"])
    # спецификация справа не спорит с блоком: та же цена
    assert "<dt>Стоимость</dt><dd>500 ₽, дети и пенсионеры бесплатно</dd>" in html


# Все опубликованные карточки мест сайта, кроме отложенных (мост 49 и пустынь 30).
_ALL_CARDS = [
    24, 25, 27, 29, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 48, 50, 51, 52,
    53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71,
    72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90,
    91, 92, 93, 94, 99, 102, 103, 105,
]
_POSTPONED = {30, 49}


def test_practical_block_on_all_cards_except_postponed():
    for pid in _ALL_CARDS:
        cfg = seo.PLACE_PRACTICAL[pid]
        assert any(cfg.get(k) for k, _ in seo.PRACTICAL_LABELS), pid
    for pid in _POSTPONED:
        assert pid not in seo.PLACE_PRACTICAL


def test_new_official_facts_and_varied_titles():
    assert seo.place_facts(68)["price"] == 1500
    assert seo.place_facts(72)["price"] == 650
    assert seo.place_facts(77)["price"] == 200
    assert seo.place_facts(83)["price"] == 100
    assert seo.place_facts(69)["price"] == 100
    assert seo.place_facts(41)["price"] == 0
    assert seo.place_facts(85)["price"] == 0
    assert seo.fact_title(67, "x") == "«АкваТермо» в Тульском: часы работы и цены 2026"
    assert seo.fact_title(68, "x") == "«Кедровый бор» в Цветочном: часы работы и цены 2026"
    assert seo.fact_title(72, "x") == "Термы Псыгупс: часы работы и цены 2026"
    assert seo.fact_title(77, "x") == "Картинная галерея Адыгеи: режим работы и билеты 2026"
    assert seo.fact_title(41, "x") == "Долина аммонитов: вход свободный, как добраться"
    # закрытые маршруты заповедника — в тексте, без разметки часов как «открыто»
    assert seo.place_facts(29) is None and "закрыт" in seo.PLACE_PRACTICAL[29]["hours"]["text"]
    assert seo.place_facts(66) is None and "закрыт" in seo.PLACE_PRACTICAL[66]["hours"]["text"]
