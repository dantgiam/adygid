"""Голый adygid.ru уводит на www с тем же путём, а HEAD отвечает как GET без тела."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("host", ["adygid.ru", "ADYGID.RU", "adygid.ru:443", "adygid.ru."])
def test_bare_domain_redirects_to_www(client, host):
    r = client.get("/", headers={"host": host}, follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "https://www.adygid.ru/"


def test_redirect_keeps_path_and_query(client):
    r = client.get("/mesta/54?utm_source=max&x=%D0%B0", headers={"host": "adygid.ru"},
                   follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "https://www.adygid.ru/mesta/54?utm_source=max&x=%D0%B0"


def test_redirect_for_head_and_post(client):
    for method in ("HEAD", "POST"):
        r = client.request(method, "/podbor", headers={"host": "adygid.ru"}, follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"] == "https://www.adygid.ru/podbor"


def test_www_is_not_redirected(client):
    r = client.get("/privacy", headers={"host": "www.adygid.ru"}, follow_redirects=False)
    assert r.status_code == 200


@pytest.mark.parametrize("path", ["/", "/privacy", "/robots.txt", "/assets/site.css"])
def test_head_matches_get_without_body(client, path):
    get = client.get(path, headers={"host": "www.adygid.ru"})
    head = client.head(path, headers={"host": "www.adygid.ru"})
    assert get.status_code == 200
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers.get("content-type") == get.headers.get("content-type")


def test_head_on_missing_page_is_404_not_405(client):
    r = client.head("/no-such-page-xyz", headers={"host": "www.adygid.ru"})
    assert r.status_code == 404
