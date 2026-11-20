"""Топ-10 «Коротко для поездки»: блок на странице и ссылки на первоисточники.

facts не заводим: у этих карточек нет часов открытия/закрытия, которые можно
честно положить в JSON-LD. Закрытые маршруты заповедника так и остаются
без разметки «открыто»."""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])

# id → фрагмент текста, который должен быть виден, и который мы сверили с источником.
SOURCED = {
    52: "около 4 км",
    45: "Карла Маркса, 61",
    50: "Чёртов палец",
    29: "полностью закрыт",
    61: "только пешком",
    66: "приют Фишт",
    75: "бесплатный",
}
# Официальной страницы с фактами для блока нет — карточку не наполняли.
SKIPPED = (40, 42, 57)


def _row_sources(cfg: dict) -> list:
    urls = []
    for key, _label in seo.PRACTICAL_LABELS:
        value = cfg.get(key)
        if isinstance(value, dict) and value.get("source"):
            urls.append(value["source"])
    return urls


@pytest.fixture()
def client():
    return TestClient(app)


def test_sourced_cards_have_links_and_no_jsonld_facts():
    for pid, snippet in SOURCED.items():
        cfg = seo.PLACE_PRACTICAL[pid]
        assert seo.place_facts(pid) is None, pid
        assert "facts" not in cfg and "checked" not in cfg and "sources" not in cfg
        urls = _row_sources(cfg)
        assert urls, pid
        assert all(url.startswith("https://") for url in urls)
        text = " ".join(
            cfg[k]["text"] if isinstance(cfg.get(k), dict) else cfg[k]
            for k, _ in seo.PRACTICAL_LABELS
            if isinstance(cfg.get(k), str) or (isinstance(cfg.get(k), dict) and "text" in cfg[k])
        )
        assert snippet in text, pid


def test_skipped_cards_stay_without_official_facts():
    for pid in SKIPPED:
        cfg = seo.PLACE_PRACTICAL[pid]
        assert seo.place_facts(pid) is None
        assert _row_sources(cfg) == []
        assert any(cfg.get(k) for k, _ in seo.PRACTICAL_LABELS)


def test_sourced_block_renders_with_source_links(client, monkeypatch):
    created = client.post(
        "/api/checkpoints",
        json={"name": "Проверка источников", "lon": 40.2, "lat": 44.2, "is_paid": False},
        auth=AUTH,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    for place_id, snippet in SOURCED.items():
        cfg = {k: v for k, v in seo.PLACE_PRACTICAL[place_id].items() if k != "route"}
        cfg["combine"] = []
        monkeypatch.setitem(seo.PLACE_PRACTICAL, pid, cfg)
        html = client.get(f"/mesta/{pid}").text
        assert "Коротко для поездки" in html
        assert '<table class="practical-table">' in html
        assert snippet in html
        assert 'class="practical-src"' in html
        for url in _row_sources(cfg):
            assert url in html
        assert "openingHoursSpecification" not in html
