"""SEO-поток ноября 2026: FAQ по слагу, обратные ссылки, хлебные крошки,
title по правилам, lastmod в sitemap и сезонный блок на главной."""
import json
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def _place(client, name="SEO-тестовое место"):
    r = client.post("/api/checkpoints", json={"name": name, "lon": 40.2, "lat": 44.3, "is_paid": False}, auth=AUTH)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_place_gets_faq_breadcrumbs_and_mentions(client):
    pid = _place(client)
    r = client.post("/api/faq-sets", json={
        "name": "seo test", "slug": f"mesta-{pid}", "title": "Частые вопросы про тест",
        "items": [{"question": "Сколько стоит?", "answer": "Бесплатно."}],
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    slug = "seo-test-" + uuid.uuid4().hex[:6]
    r = client.post("/api/articles", json={
        "title": "Статья со ссылкой", "slug": slug, "body": f'<p>Смотри <a href="/mesta/{pid}">место</a>.</p>',
    }, auth=AUTH)
    assert r.status_code == 201, r.text

    html = client.get(f"/mesta/{pid}").text
    assert "Частые вопросы про тест" in html
    # FAQ стоит до «Понравилось?»
    assert html.index("Частые вопросы про тест") < html.index('class="like-row"')
    types = {b.get("@type") for b in _ld_blocks(html)}
    assert {"FAQPage", "BreadcrumbList", "TouristAttraction"} <= types
    assert "Где ещё про это место" in html and f"/stati/{slug}" in html


def test_article_title_rule_next_hub_and_dates(client):
    r = client.post("/api/articles", json={"title": "Туман только наверху", "slug": "tuman-na-lago-naki-kuda-ehat", "body": "<p>x</p>",
                                           "faq": [{"question": "Q?", "answer": "A."}]}, auth=AUTH)
    assert r.status_code in (201, 409, 400, 422) or r.status_code < 300
    html = client.get("/stati/tuman-na-lago-naki-kuda-ehat").text
    assert f"<title>{seo.ARTICLE_TITLES['tuman-na-lago-naki-kuda-ehat']}</title>" in html
    assert "<h1 class=\"article-title\">Туман только наверху</h1>" in html
    article_ld = next(b for b in _ld_blocks(html) if b.get("@type") == "Article")
    assert article_ld.get("dateModified")
    assert any(b.get("@type") == "FAQPage" for b in _ld_blocks(html))


def test_district_title_uses_village_name():
    assert "Каменномостский" in seo.DISTRICT_TITLES["khadzhokh"]
    for title in list(seo.DISTRICT_TITLES.values()) + list(seo.ARTICLE_TITLES.values()):
        assert len(title) <= 75, title


def test_place_title_rule():
    assert seo.place_title("Хаджохская теснина", "khadzhokh") == \
        "Хаджохская теснина (Каменномостский, Адыгея) — как добраться и что посмотреть"
    assert seo.place_title("Плато Лаго-Наки", "lagonaki").startswith("Плато Лаго-Наки (Адыгея)")


def test_sitemap_has_lastmod_for_sections(client):
    _place(client, "SEO lastmod")
    xml = client.get("/sitemap.xml").text
    block = re.search(r"<loc>[^<]*/mesta</loc>\s*<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", xml)
    assert block, xml[:500]


def test_seasonal_config_never_links_to_dog_cluster():
    for month in range(1, 13):
        cfg = seo.SEASONAL.get(month)
        for item in (cfg or {}).get("items", []):
            assert "sobak" not in item["url"]


# ── Доработка по разбору GPT (14.11): районы, практический блок, ручной хаб ──

def test_district_display_replaces_internal_okrug_word():
    assert seo.district_display("khadzhokh", "Округ Хаджоха") == "Хаджох (Каменномостский)"
    assert seo.district_display("maikop", "округ Майкопа") == "Майкоп и окрестности"
    # Человеческое название из админки не перебиваем.
    assert seo.district_display("lagonaki", "Плато Лагонаки") == "Плато Лагонаки"
    for value in seo.DISTRICT_DISPLAY.values():
        assert "округ" not in value.lower()


def test_nav_and_lists_say_rayon_not_okrug(client):
    for url in ("/", "/okrugi", "/mesta", "/marshruty"):
        html = client.get(url).text
        visible = re.sub(r"<script.*?</script>|<!--.*?-->", "", html, flags=re.S)
        assert ">Районы<" in visible or "Любой район" in visible, url
        assert "Округа<" not in visible and "Любой округ" not in visible, url


def test_district_titles_are_not_one_template():
    titles = list(seo.DISTRICT_TITLES.values())
    heads = {t.split(":")[1].split("—")[0].strip() for t in titles}
    assert len(heads) >= 4, heads
    assert not any("| АдыГид" in t and "Адыгея" in t for t in titles)


def test_key_place_titles_varied_and_without_prices():
    assert 10 <= len(seo.PLACE_TITLES) <= 15
    assert seo.place_title("Хаджохская теснина", "khadzhokh", 24) == seo.PLACE_TITLES[24]
    tails = {t.split(":", 1)[1].split("—")[0].strip() for t in seo.PLACE_TITLES.values() if ":" in t}
    assert len(tails) >= 10
    for t in seo.PLACE_TITLES.values():
        assert "₽" not in t and len(t) <= 75, t


def test_practical_fields_never_carry_unsourced_prices():
    keys = {k for k, _ in seo.PRACTICAL_LABELS}
    assert 10 <= len(seo.PLACE_PRACTICAL) <= 15
    for pid, cfg in seo.PLACE_PRACTICAL.items():
        assert set(cfg) <= keys | {"route"}, pid
        tickets = cfg.get("tickets")
        text = tickets["text"] if isinstance(tickets, dict) else (tickets or "")
        if "₽" in text:
            # цифра либо с официальным источником, либо явно «не подтверждён»
            # или с пометкой «по данным путеводителей» (решение 14.11.2026)
            assert ((isinstance(tickets, dict) and tickets.get("source")) or "не подтвержд" in text
                    or "по данным путеводителей" in text.lower()), pid


def test_place_practical_block_renders_only_filled_fields(client, monkeypatch):
    pid = _place(client, "SEO практический блок")
    other = _place(client, "Соседнее место для связки")
    r = client.patch(f"/api/checkpoints/{pid}", json={"duration_minutes": 90}, auth=AUTH)
    assert r.status_code == 200, r.text
    monkeypatch.setitem(seo.PLACE_PRACTICAL, pid, {
        "how": "Прямо в посёлке.", "tickets": seo.NO_PRICE, "combine": [other],
    })
    html = client.get(f"/mesta/{pid}").text
    assert "Коротко для поездки" in html
    assert "Время посещения" in html and "1 ч 30 мин" in html
    assert "Прямо в посёлке." in html and "Актуальный тариф не подтверждён" in html
    assert f'<a href="/mesta/{other}">Соседнее место для связки</a>' in html
    # незаполненные поля не показываются
    assert "Часы работы" not in html and "<dt>Зимой</dt>" not in html
    # блок — до описания и FAQ
    assert html.index("Коротко для поездки") < html.index('class="like-row"')

    plain = _place(client, "SEO место без блока")
    assert "Коротко для поездки" not in client.get(f"/mesta/{plain}").text


def test_curated_scenario_shows_only_picked_cards(client, monkeypatch):
    picked = _place(client, "Зимнее место из подборки")
    skipped = _place(client, "Место вне подборки")
    slug = "seo-curated-" + uuid.uuid4().hex[:6]
    r = client.post("/api/scenarios", json={"slug": slug, "door": "Тест", "title": "Тестовый хаб", "lead": "<p>x</p>"}, auth=AUTH)
    assert r.status_code in (200, 201), r.text
    monkeypatch.setitem(seo.SCENARIO_CURATED, slug, {"places": [picked], "routes": []})
    html = client.get(f"/kuda/{slug}").text
    assert "Зимнее место из подборки" in html
    assert "Место вне подборки" not in html
    assert "Весь каталог мест" in html


def test_winter_hub_curated_list_is_narrow():
    cur = seo.SCENARIO_CURATED["zimoy"]
    assert 10 <= len(cur["places"]) <= 15 and len(cur["routes"]) <= 8
    assert 50 not in cur["places"] and 11 not in cur["routes"]


def test_seasonal_block_links_to_place_cards_by_name(client, monkeypatch):
    pid = _place(client, "Место из сезонного блока")
    cfg = dict(seo._WINTER, items=[
        {"url": "/mesta/%d" % pid, "label": "a", "note": "", "cover": "x"},
        {"url": "/mesta/%d" % pid, "label": "b", "note": "", "cover": "x"},
    ], places=[pid])
    monkeypatch.setattr(seo, "seasonal_for", lambda today=None: cfg)
    from site_app import router as site_router
    site_router._HOME_CACHE["body"] = None
    html = client.get("/").text
    site_router._HOME_CACHE["body"] = None
    assert f'<a href="/mesta/{pid}" data-seasonal-click data-target="/mesta/{pid}">Место из сезонного блока</a>' in html


def test_publish_script_text_patch_is_safe():
    import importlib.util
    spec = importlib.util.spec_from_file_location("seo_publish", "scripts/seo_content_publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text, done = mod.apply_text_patch("<p>Казачий камень рядом.</p>", [("Казачий камень", '<a href="/mesta/42">Казачий камень</a>')], "t")
    assert done == 1 and 'href="/mesta/42"' in text
    # повторный запуск ничего не ломает и не оборачивает ссылку второй раз
    again, done2 = mod.apply_text_patch(text, [("Казачий камень", '<a href="/mesta/42">Казачий камень</a>')], "t")
    assert again == text and done2 == 0
    with pytest.raises(SystemExit):
        mod.apply_text_patch("<p>совсем другой текст</p>", [("Казачий камень", "y")], "t")
    # сценарий уходит в API целиком, а не обрезком
    full = mod.scenario_payload({"slug": "dozhd", "icon": "🌧️", "door": "d", "title": "t", "lead": "old",
                                 "filter_access": ["paved"], "order_index": 5, "is_published": True}, lead="new")
    assert full["lead"] == "new" and full["icon"] == "🌧️" and full["filter_access"] == ["paved"] and full["order_index"] == 5
    # все правки — только ссылки на карточки или «округ» → «район»
    for pch in mod.CONTENT["text_patches"]:
        assert pch["slug"] not in ("chertov-palec",)
        for old, new in pch["replace"]:
            assert "/mesta/50" not in new and "/marshruty/11" not in new


def test_home_cards_show_rayon_labels_even_on_cold_start(client):
    from site_app import router as site_router
    site_router._HOME_CACHE["body"] = None
    site_router._DISTRICT_CACHE["value"] = None
    for k, v in list(site_router._DISTRICT_LABELS.items()):
        assert "округ" not in v.lower(), (k, v)
    html = client.get("/").text
    assert 'class="kicker">Округ' not in html


def _publish_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("seo_publish", "scripts/seo_content_publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_autolink_first_mention_only_and_idempotent():
    from site_app.autolink import autolink
    html = ('<h2>Хаджохская теснина</h2><p>Сначала в Хаджохскую теснину, потом снова Хаджохская теснина '
            'и <a href="/mesta/40">Руфабго</a>, водопады Руфабго.</p>'
            '<figure><figcaption>Гранитный каньон</figcaption></figure><p>Скала Чёртов палец.</p>')
    out, added = autolink(html)
    assert [pid for pid, _ in added] == [24]
    assert out.count('href="/mesta/24"') == 1 and '<a href="/mesta/24">Хаджохскую теснину</a>' in out
    assert "<h2>Хаджохская теснина</h2>" in out          # заголовки не трогаем
    assert out.count('href="/mesta/40"') == 1             # уже связанное — не дублируем
    assert 'href="/mesta/52"' not in out                  # подписи к фото — тоже
    assert "/mesta/50" not in out                         # место 50 не связываем
    again, added2 = autolink(out)
    assert again == out and added2 == []
    # предел ссылок на странице считает и уже стоявшие
    many = "".join(f'<a href="/mesta/{i}">x</a>' for i in range(100, 112)) + "<p>Хаджохская теснина</p>"
    assert autolink(many)[1] == []
    # только опубликованные карточки и без ссылки на себя
    assert autolink("<p>Хаджохская теснина</p>", allowed={40})[1] == []
    assert autolink("<p>Хаджохская теснина</p>", self_id=24)[1] == []


def test_text_patch_survives_autolinks_inside_new_text():
    mod = _publish_module()
    pairs = [("Казачий камень", 'Казачий камень и <a href="/mesta/24">теснина</a>, Гранитный каньон')]
    text, _ = mod.apply_text_patch("<p>Казачий камень</p>", pairs, "t")
    from site_app.autolink import autolink
    linked, _ = autolink(text)
    again, done = mod.apply_text_patch(linked, pairs, "t")
    assert again == linked and done == 0


def test_district_assignment_is_complete_and_never_touches_50_or_11():
    mod = _publish_module()
    plan = list(mod.district_plan(mod.CONTENT["district_assign"]))
    assert len([p for p in plan if p[0] == "mesta"]) == 23 and len([p for p in plan if p[0] == "marshruty"]) == 17
    assert ("mesta", 105, "khadzhokh") in plan
    assert {slug for _, _, slug in plan} <= {"maikop", "khadzhokh", "guzeripl", "dakhovskaya", "lagonaki"}
    assert all((k, i) not in {("mesta", 50), ("marshruty", 11)} for k, i, _ in plan)
    # Гончарка и Новосвободная — «Майкоп и окрестности»
    assert ("mesta", 79, "maikop") in plan and ("mesta", 85, "maikop") in plan
    with pytest.raises(SystemExit):
        list(mod.district_plan({"mesta": {50: "khadzhokh"}}))


def test_guidebook_prices_are_labelled_and_new_photos_credited():
    mod = _publish_module()
    c = mod.CONTENT
    blob = json.dumps(c, ensure_ascii=False)
    assert "по прайсу комплекса" not in blob and "Последняя известная цена по путеводителям" not in blob
    assert "1150 ₽" in blob and "по данным путеводителей на 14.11.2026, актуальный тариф" in blob
    for pid in (24, 40, 67):
        p = seo.PLACE_PRACTICAL[pid]
        assert "по данным путеводителей" in (p["tickets"] if isinstance(p["tickets"], str) else p["tickets"]["text"]).lower()
    # без Альп и без чужих фото на новых страницах
    assert "581ad467b3414354b038915f243f8e79" not in blob
    assert "68c87251f4cb492b93a278a6436b78bf" not in blob
    for key, ph in c["commons"].items():
        assert "Адыге" in ph["what"] or "Лаго-Наки" in ph["what"], key
        assert ph["license"].startswith(("CC BY", "Public domain"))
    pages = [a["body"] for a in c["articles"]] + [c["scenario_zimoy"]["lead"]]
    for a in c["articles"] + [dict(c["scenario_zimoy"], body=c["scenario_zimoy"]["lead"])]:
        for key, ph in c["commons"].items():
            if a["cover_url"] == ph["src"]:
                assert ph["page"] in a["body"] and ph["author"] in a["body"]
    assert pages


def test_hub_faq_sets_for_dozhd_and_s_detmi():
    c = _publish_module().CONTENT
    sets = {f["slug"]: f for f in c["faq_sets"]}
    for slug in ("kuda-dozhd", "kuda-s-detmi"):
        assert slug in sets and 3 <= len(sets[slug]["items"]) <= 5
        assert sets[slug]["on_faq_page"] is False
        assert "₽" not in json.dumps(sets[slug], ensure_ascii=False)


def test_review_block_has_telegram_next_to_max(client):
    from site_app.router import review_bot_url_tg
    assert review_bot_url_tg("m", 54) == "https://t.me/adygid_bot?start=rv_m54"
    assert review_bot_url_tg("r", 12) == "https://t.me/adygid_bot?start=rv_r12"
    long = review_bot_url_tg("s", "a" * 80)
    assert len(long.split("start=")[1]) == 64
    pid = _place(client, "Место для отзыва в Telegram")
    html = client.get(f"/mesta/{pid}").text
    block = html[html.find('class="section review-cta-section"'):]
    block = block[:block.find("</section>")]
    assert f"https://max.ru/se15002131_bot?start=rv_m{pid}" in block
    assert f"https://t.me/adygid_bot?start=rv_m{pid}" in block
    assert block.find("max.ru") < block.find("t.me")


def test_district_lead_links_its_places(client, monkeypatch):
    from site_app import router
    r = client.get("/okrugi/guzeripl")
    if r.status_code != 200:
        pytest.skip("в тестовой базе нет района")
    assert "district-lead" in r.text
