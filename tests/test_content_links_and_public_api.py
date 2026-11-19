"""Ссылки в опубликованном контенте не ведут в 404, а открытые GET /api/*
не отдают черновики (статьи, маршруты, места, хабы и прочее) без пароля админки."""
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.content_fixes import fix_stop_links
from app.database import SessionLocal
from app.main import app
from app.models import Article, Checkpoint, Scenario, Trail
from site_app import urls as site_urls

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def _uid():
    return "".join("абвгдежзиклмнопрстуф"[int(c, 16)] for c in uuid.uuid4().hex[:6])


def _post(client, path, body):
    if path in ("/api/checkpoints", "/api/trails"):
        body = {"is_paid": False, **body}  # NULL в is_paid ломает test_cost_status на общей базе
    r = client.post(path, json=body, auth=AUTH)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ── маршрут «Уна-Коз понизу»: ссылки на точки без страницы ─────────────

def test_route_stop_links_go_to_real_places_or_stop_anchor(client):
    savr = _post(client, "/api/checkpoints", {"name": "Савранская канатная дорога", "lon": 40.1, "lat": 44.1, "is_paid": True})
    _post(client, "/api/checkpoints", {"name": "Скала Чёртов палец", "lon": 40.1, "lat": 44.1, "is_paid": False})
    t = _post(client, "/api/trails", {"name": f"Уна-Коз понизу {_uid()}: гроты", "is_paid": False})
    stops = {}
    for name in ("Старт: верхняя станция Савранской канатной дороги", "Вход в пещеру Пыльную на нижней тропе", "Выход к Чёртову пальцу"):
        stops[name] = _post(client, "/api/checkpoints", {"name": name, "trail_id": t["id"], "lon": 40.1, "lat": 44.1})
        assert stops[name]["url"] is None  # точка маршрута — без своей страницы
    s1, s2, s3 = (stops[n]["id"] for n in stops)
    desc = (f'<ol><li><a href="/mesta/{s1}">Старт</a></li><li><a href="/mesta/{s2}">Пыльная</a></li>'
            f'<li><a href="/mesta/{s3}">Чёртов палец</a></li></ol>')
    assert client.patch(f"/api/trails/{t['id']}", json={"description": desc}, auth=AUTH).status_code == 200

    with SessionLocal() as db:
        assert fix_stop_links(db) >= 2
        db.commit()
        assert fix_stop_links(db) == 0  # повторный старт ничего не меняет
        fixed = db.get(Trail, t["id"]).description
        names = dict(db.execute(select(Checkpoint.id, Checkpoint.name)).all())
    linked = [int(i) for i in re.findall(r'href="/mesta/(\d+)"', fixed)]
    assert f'href="/mesta/{s1}"' not in fixed and f'href="/mesta/{s3}"' not in fixed
    assert [names[i] for i in linked] == ["Савранская канатная дорога", f"{names[s2]}", "Скала Чёртов палец"]

    site_urls.invalidate()
    page = client.get(t["url"])
    html = page.text
    assert f'href="{t["url"]}#stop-{s2}"' in html and f'id="stop-{s2}"' in html
    assert f'href="{savr["url"]}"' in html or 'href="/mesta/savranskaya-kanatnaya-doroga' in html
    # старый прямой адрес точки — на её строку в маршруте, а не 404
    r = client.get(f"/mesta/{s2}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"{t['url']}#stop-{s2}"


_INTERNAL = re.compile(r'href="(?:https?://(?:www\.)?adygid\.ru)?(/(?:mesta|marshruty|stati|kuda|okrugi)/[^"#?]*)')


def test_no_internal_link_in_published_content_is_404(client):
    """Каждая внутренняя ссылка из опубликованных статей, хабов, маршрутов и
    мест открывается (после 301, если адрес старый)."""
    site_urls.invalidate()
    with SessionLocal() as db:
        texts = [a.body for a in db.execute(select(Article).where(Article.is_published == True)).scalars()]
        texts += [s.lead for s in db.execute(select(Scenario).where(Scenario.is_published == True)).scalars()]
        texts += [t.description for t in db.execute(select(Trail).where(Trail.is_published == True)).scalars()]
        texts += [c.description for c in db.execute(select(Checkpoint).where(
            Checkpoint.is_published == True, Checkpoint.show_as_place == True)).scalars()]
    hrefs = {h for txt in texts if txt for h in _INTERNAL.findall(site_urls.rewrite_links(txt))}
    bad = [(h, s) for h in sorted(hrefs) for s in [client.get(h).status_code] if s == 404]
    assert not bad, bad


# ── открытые API без черновиков ──────────────────────────────────────

def test_public_api_hides_unpublished(client):
    u = _uid()
    art = _post(client, "/api/articles", {"title": f"Черновик {u}", "slug": f"draft-{uuid.uuid4().hex[:6]}",
                                          "body": "<p>секретный черновик</p>", "is_published": False})
    pub = _post(client, "/api/articles", {"title": f"Опубликовано {u}", "slug": f"pub-{uuid.uuid4().hex[:6]}",
                                          "body": "<p>x</p>", "is_published": True})
    trail = _post(client, "/api/trails", {"name": f"Скрытый маршрут {u}", "is_published": False, "is_paid": False})
    stop = _post(client, "/api/checkpoints", {"name": f"Точка скрытого {u}", "trail_id": trail["id"], "lon": 40.0, "lat": 44.0})
    place = _post(client, "/api/checkpoints", {"name": f"Скрытое место {u}", "lon": 40.0, "lat": 44.0, "is_published": False})
    sc = _post(client, "/api/scenarios", {"slug": f"draft-hub-{uuid.uuid4().hex[:6]}", "door": "x", "title": f"Хаб {u}",
                                          "lead": "<p>x</p>", "is_published": False})

    anon = TestClient(app)
    ids = lambda path: {x["id"] for x in anon.get(path).json()}
    assert art["id"] not in ids("/api/articles") and pub["id"] in ids("/api/articles")
    assert "секретный черновик" not in anon.get("/api/articles").text
    assert anon.get(f"/api/articles/{art['id']}").status_code == 404
    assert anon.get(f"/api/articles/{pub['id']}").status_code == 200
    assert anon.get(f"/api/articles/{art['slug']}").status_code in (404, 422)
    assert trail["id"] not in ids("/api/trails")
    for path in (f"/api/trails/{trail['id']}", f"/api/trails/{trail['id']}/segments", f"/api/trails/{trail['id']}/checkpoints"):
        assert anon.get(path).status_code == 404, path
    cps = ids("/api/checkpoints")
    assert place["id"] not in cps and stop["id"] not in cps
    near = {x["id"] for x in anon.get("/api/checkpoints/nearby?lat=44.0&lon=40.0&limit=100").json()}
    assert place["id"] not in near and stop["id"] not in near
    assert sc["id"] not in ids("/api/scenarios")
    for path in ("/api/magnets", "/api/faq-sets", "/api/districts"):
        assert all(x.get("is_published", True) for x in anon.get(path).json()), path

    # Админка (тот же Basic-пароль) видит черновики, как и раньше
    adm = lambda path: {x["id"] for x in client.get(path, auth=AUTH).json()}
    assert art["id"] in adm("/api/articles") and trail["id"] in adm("/api/trails")
    assert place["id"] in adm("/api/checkpoints") and sc["id"] in adm("/api/scenarios")
    assert client.get(f"/api/articles/{art['id']}", auth=AUTH).status_code == 200
    assert client.get(f"/api/trails/{trail['id']}", auth=AUTH).status_code == 200
    # чужой пароль — как гость
    assert art["id"] not in {x["id"] for x in anon.get("/api/articles", auth=("admin", "wrong")).json()}
