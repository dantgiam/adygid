"""Файлы подтверждения Яндекс Вебмастера открываются и не входят в sitemap."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient

from app.main import app

CODES = ("eb29101ea5533cf1", "30c724c08ddd1bbd")


def _verification_html(code: str) -> str:
    return (
        "<html>\n"
        "    <head>\n"
        '        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">\n'
        "    </head>\n"
        f"    <body>Verification: {code}</body>\n"
        "</html>"
    )


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("code", CODES)
def test_yandex_verification_file(client, code):
    page = client.get(f"/yandex_{code}.html")
    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=UTF-8"
    assert f"Verification: {code}" in page.text
    assert page.text == _verification_html(code)

    site = client.get("/sitemap.xml")
    assert site.status_code == 200
    assert f"/yandex_{code}.html" not in site.text
