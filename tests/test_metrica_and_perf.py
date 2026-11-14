"""Цели Метрики (новые идентификаторы) и безопасные правки скорости."""
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_versioned_assets_are_immutable(client):
    plain = client.get("/assets/site.css")
    assert plain.status_code == 200
    assert plain.headers.get("Cache-Control") == "public, max-age=604800"
    versioned = client.get("/assets/site.css", params={"v": "test"})
    assert versioned.status_code == 200
    assert versioned.headers.get("Cache-Control") == "public, max-age=604800, immutable"
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers.get("Cache-Control") == "no-store"


def test_base_template_has_optional_media_preconnect():
    base = (ROOT / "site_app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'rel="preconnect"' in base
    assert "media_origin" in base
    assert 'rel="dns-prefetch"' in base


def test_home_hero_is_prioritized_and_sized(client):
    src = (ROOT / "site_app" / "templates" / "home.html").read_text(encoding="utf-8")
    assert 'fetchpriority="high"' in src
    assert 'width="800" height="800"' in src
    assert 'width="800" height="500"' in src
    covers = (ROOT / "site_app" / "templates" / "_cards.html").read_text(encoding="utf-8")
    assert 'width="900" height="600"' in covers
    assert 'width="1600" height="1000"' in covers
    home = client.get("/")
    assert home.status_code == 200


def test_helper_is_safe_without_metrika_id():
    js = (ROOT / "site_app" / "static" / "site.js").read_text(encoding="utf-8")
    # Без номера счётчика цели молчат; без загруженного ym тоже не падают.
    assert "if (!window.ADYGID_METRIKA_ID) return;" in js
    assert 'if (typeof window.ym === "function") window.ym(id, "reachGoal"' in js
    assert 'consent === "necessary"' in js


def test_podbor_does_not_preload_all_photos_on_start():
    js = (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")
    assert "function startInitialPhotoPreload" in js
    assert "preloadPlacePhotos(8)" in js
    assert "requestIdleCallback" in js
    # Полный предзагруз всех фото стартует только после первого ответа.
    assert "markStart" in js
    src = js.split("function markStart")[1].split("function ")[0]
    assert "preloadPlacePhotos();" in src
