"""Alt карусели на карточке места: подпись из админки или «название, фото N»."""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def test_place_gallery_alt_uses_caption_or_name(client):
    created = client.post(
        "/api/checkpoints",
        json={"name": "Тестовая галерея", "lon": 40.136, "lat": 44.0, "is_paid": False},
        auth=AUTH,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    for body in (
        {"url": "https://example.test/cover.jpg"},
        {"url": "https://example.test/plain.jpg"},
        {"url": "https://example.test/caption.jpg", "caption": "Арка моста"},
    ):
        assert client.post(f"/api/checkpoints/{pid}/photos", json=body, auth=AUTH).status_code == 201
    html = client.get(f"/mesta/{pid}").text
    start = html.index('class="pcar"')
    block = html[start:html.index("pcar-info", start)]
    assert 'alt="Тестовая галерея, фото 1"' in block
    assert 'alt="Арка моста"' in block
    assert 'alt=""' not in block
    caption = html[html.index("pcar-caption"):html.index("pcar-caption") + 80]
    assert "Тестовая галерея, фото 1" not in caption
