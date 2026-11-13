"""Страницы /privacy и /soglasie открываются, в поиск не входят.

Подвал, базовый шаблон и подборщик здесь не проверяются на правки:
тест только читает уже существующую ссылку из подвала. Данные маршрута 11
и места 50 не записываются.
"""
import os
import re

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient

from app.main import app

OPERATOR = "Севастьянов Данила Александрович"
INN = "840111874548"
EMAIL = "adygid.privacy@mail.ru"
ADDRESS = "Республика Адыгея, г. Майкоп"
DATE = "13.11.2026"
HOST = "Яндекс.Облако"
COUNTER = "111028002"
BOT = "https://max.ru/se15002131_bot"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _main(html: str) -> str:
    start = html.find("<main>")
    end = html.find("</main>")
    assert start != -1 and end != -1
    return html[start:end]


def test_privacy_and_consent_open_for_apex_and_www(client):
    for path in ("/privacy", "/soglasie"):
        for host in ("adygid.ru", "www.adygid.ru"):
            page = client.get(path, headers={"Host": host})
            assert page.status_code == 200, (path, host, page.status_code)
            assert "noindex" in page.text
            assert "<h1" in page.text


def test_published_text_has_no_placeholders(client):
    for path in ("/privacy", "/soglasie"):
        main = _main(client.get(path).text)
        assert "[" not in main and "]" not in main
        assert "Вариант" not in main
        assert "Telegram" not in main and "Телеграм" not in main
        assert OPERATOR in main
        assert INN in main
        assert EMAIL in main
        assert ADDRESS in main
        assert DATE in main
        assert HOST in main
        assert "не присвоен" in main
        assert not re.search(r"\+7|\b8\s*\(\d{3}\)", main)


def test_privacy_covers_live_processes_and_has_toc(client):
    main = _main(client.get("/privacy").text)
    assert 'href="#s1"' in main
    assert 'id="s3-1"' in main
    assert 'id="s6"' in main
    assert COUNTER in main
    assert BOT in main
    assert "Только необходимые" in main
    assert "можно пропустить" in main
    assert "анкета поставщика услуг" in main
    assert "Анкета поставщика услуг (местного бизнеса)" not in main
    assert 'href="/soglasie"' in main
    assert "трансграничн" in main.lower()
    assert "не осуществляется" in main


def test_consent_links_policy_and_keeps_supplier_conditional(client):
    main = _main(client.get("/soglasie").text)
    assert "https://www.adygid.ru/privacy" in main
    assert "если я её заполняю" in main
    assert "мессенджере MAX" in main
    assert "не осуществляется" in main


def test_distribution_consent_is_not_published(client):
    missing = client.get("/soglasie-rasprostranenie")
    assert missing.status_code == 404


def test_legal_pages_stay_out_of_sitemap_and_footer_link_resolves(client):
    site = client.get("/sitemap.xml")
    assert site.status_code == 200
    assert "/privacy" not in site.text
    assert "/soglasie" not in site.text

    home = client.get("/")
    assert 'href="/privacy"' in home.text
    assert client.get("/privacy").status_code == 200
