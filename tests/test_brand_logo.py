"""Шапка, подвал и Organization носят кота, а не горы."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def test_header_footer_and_organization_use_the_cat(client):
    html = client.get("/").text
    assert "/assets/logo-cat.png" in html
    assert "9BCBA4" not in html
    assert html.count("logo-cat.png") >= 3  # шапка, подвал и разметка
    org = next(b for b in _ld_blocks(html) if b.get("@type") == "Organization")
    assert org["name"] == "АдыГид"
    assert org["logo"].endswith("/assets/logo-cat.png")
    assert ">АдыГид</span>" in html
