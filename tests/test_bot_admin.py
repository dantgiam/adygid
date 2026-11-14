"""Страницы админки бота: входящие и шаблоны.

API бота подменён. Обращения не пишутся в базу сайта, токен и тело ответа
не попадают в HTML и в журнал.
"""
import json
import logging
import os

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

from app import bot_admin

AUTH = ("admin", "adygid-test")
TOKEN = "test-token-not-for-browser"
QUESTION_ID = "3f0c9a52-6a1e-4f7e-9a51-1b2c3d4e5f60"
REVIEW_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SERVICE_ID = "11111111-2222-4333-8444-555555555555"
TG_QUESTION_ID = "aaaaaaaa-1111-4222-8333-444444444444"
LONG_REVIEW = "Оставить отзыв о месте или маршруте"
SECRET_BODY = "секретное обращение Данила"
SECRET_LEAK = "секретный-телефон-+79990001122"
SECRET_TOKEN = "secret-attachment-token"


def _limits():
    return {"text_max": 4000, "button_max": 128, "button_recommended": 20}


def _template(**overrides):
    raw = {
        "key": "question.ask",
        "branch": "question",
        "title": "Просьба написать вопрос",
        "description": "После кнопки «Задать вопрос». Под текстом — «Отмена».",
        "kind": "message",
        "text": "Напишите вопрос, {name}",
        "buttons": None,
        "default_text": "Напишите вопрос, {name}",
        "default_buttons": None,
        "placeholders": ["name"],
        "required_placeholders": [],
        "is_default": True,
        "updated_at": "2026-11-13T14:47:12+00:00",
        "updated_by": "seed",
        "limits": _limits(),
    }
    raw.update(overrides)
    return raw


def _branches():
    return {
        "branches": [
            {"branch": "start", "title": "Старт и согласие", "templates": [
                _template(key="start.greeting", branch="start", title="Приветствие",
                          description="Первое сообщение после /start или нажатия «Начать».",
                          text="Здравствуйте, {name}!", placeholders=["name"]),
                _template(key="start.consent", branch="start", title="Согласие на обработку ПД",
                          description="Сразу после приветствия, пока человек не нажал «Согласен».",
                          text="Политика: {policy_url}",
                          buttons={"consent": "Согласен", "policy": "Политика"},
                          default_buttons={"consent": "Согласен", "policy": "Политика"},
                          placeholders=["name", "policy_url"]),
                _template(key="start.policy_url", branch="start", title="Ссылка на политику ПД",
                          description="Адрес страницы политики.", kind="url",
                          text="https://www.adygid.ru/privacy", placeholders=[]),
            ]},
            {"branch": "menu", "title": "Меню", "templates": [
                _template(key="menu.main", branch="menu", title="Главное меню",
                          description="После согласия и после каждого «Спасибо».",
                          text="Чем могу помочь?",
                          buttons={"question": "Задать вопрос", "review": LONG_REVIEW},
                          default_buttons={"question": "Задать вопрос", "review": LONG_REVIEW},
                          is_default=False, updated_by="Анна"),
            ]},
            {"branch": "question", "title": "Вопрос", "templates": [
                _template(),
            ]},
            {"branch": "review", "title": "Отзыв о месте или маршруте", "templates": [
                _template(key="review.ask", branch="review", title="Просьба написать отзыв",
                          description="После кнопки отзыва.", text="Напишите отзыв."),
            ]},
            {"branch": "service", "title": "Заявка на услугу", "templates": [
                _template(key="service.ask_type", branch="service", title="Выбор услуги",
                          description="После кнопки заявки.", text="Что хотите заказать?",
                          buttons={"rafting": "Рафтинг"}, default_buttons={"rafting": "Рафтинг"}),
            ]},
            {"branch": "podbor", "title": "Обратная связь по подборщику", "templates": [
                _template(key="podbor.ask", branch="podbor", title="Просьба об отзыве на подбор",
                          description="После кнопки отзыва о подборе.", text="Расскажите, как маршрут."),
            ]},
            {"branch": "admin", "title": "Уведомления админу", "templates": [
                _template(key="admin.notify", branch="admin", title="Уведомление о новом обращении",
                          description="Мгновенно в рабочий чат и в личку админам.",
                          text="{title}\n№ {id}", placeholders=["title", "id"],
                          required_placeholders=["title", "id"]),
                _template(key="admin.kind_titles", branch="admin", title="Названия типов обращений",
                          description="Подписи в входящих.", kind="labels", text="Типы обращений",
                          buttons={
                              "question": "❓ Вопрос гостя",
                              "review": "⭐ Отзыв о месте/маршруте",
                              "service_request": "🧭 Заявка на услугу",
                              "podbor_feedback": "🗺 Отзыв о подобранном маршруте",
                              "consent_revoked": "⚠️ Отзыв согласия на обработку ПД",
                          }, placeholders=[]),
            ]},
            {"branch": "other", "title": "Ошибки и прочее", "templates": [
                _template(key="other.error", branch="other", title="Ошибка",
                          description="Если при обработке что-то сломалось.",
                          text="Ой, что-то пошло не так."),
            ]},
        ]
    }


def _items():
    return [
        {
            "id": QUESTION_ID,
            "created_at": "2026-11-13T14:52:10.120000+00:00",
            "updated_at": "2026-11-13T14:52:10.120000+00:00",
            "user_id": 216290224,
            "user_name": "Данила",
            "kind": "question",
            "text": "Как пройти к водопадам? <script>alert(1)</script>",
            "payload": {"free_text": True},
            "status": "new",
            "notified": True,
            "platform": "max",
        },
        {
            "id": TG_QUESTION_ID,
            "created_at": "2026-11-14T08:00:00+00:00",
            "updated_at": "2026-11-14T08:00:00+00:00",
            "user_id": 866973179,
            "user_name": "Игорь",
            "kind": "question",
            "text": "Зимой открыт Хаджох?",
            "payload": {"channel": "tg", "free_text": True},
            "status": "new",
            "notified": True,
            "platform": "telegram",
        },
        {
            "id": REVIEW_ID,
            "created_at": "2026-11-13T12:00:00+00:00",
            "updated_at": "2026-11-13T12:10:00+00:00",
            "user_id": 100,
            "user_name": "Анна",
            "kind": "review",
            "text": "Руфабго понравился",
            "payload": {},
            "status": "in_progress",
            "notified": False,
        },
        {
            "id": SERVICE_ID,
            "created_at": "2026-11-13T11:00:00+00:00",
            "updated_at": "2026-11-13T11:00:00+00:00",
            "user_id": 7,
            "user_name": "Марина",
            "kind": "service_request",
            "text": None,
            "payload": {
                "service": "Рафтинг",
                "when": "20–22 ноября",
                "people": "3 взрослых",
                "phone": "+7 900 000-00-00",
                "comment": "Хочется тихую воду",
                "start_payload": "podbor_feedback_abc123",
                "attachments": [{
                    "type": "image",
                    "url": "https://files.example.test/pic.jpg",
                    "token": SECRET_TOKEN,
                }],
            },
            "status": "new",
            "notified": True,
        },
    ]


@pytest.fixture
def api_state():
    return {"requests": [], "fail": None}


@pytest.fixture
def client(monkeypatch, api_state):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adygid-test")
    monkeypatch.setenv("BOT_API_TOKEN", TOKEN)
    monkeypatch.setenv("BOT_API_URL", "https://bot.example.test/")

    def handler(request: httpx.Request) -> httpx.Response:
        api_state["requests"].append(request)
        if api_state["fail"] == "down":
            return httpx.Response(500, text=SECRET_BODY)
        if api_state["fail"] == "unauthorized":
            return httpx.Response(401, json={"error": "unauthorized"})
        if api_state["fail"] == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/inbox":
            status = request.url.params.get("status")
            items = _items()
            if status:
                items = [item for item in items if item["status"] == status]
            return httpx.Response(200, json={"items": items})
        if method == "GET" and path == "/admin/templates/admin.kind_titles":
            titles = next(
                item for branch in _branches()["branches"] if branch["branch"] == "admin"
                for item in branch["templates"] if item["key"] == "admin.kind_titles"
            )
            return httpx.Response(200, json={"template": titles})
        if method == "GET" and path == "/admin/templates":
            return httpx.Response(200, json=_branches())
        if method == "POST" and path == f"/inbox/{SERVICE_ID}/status":
            return httpx.Response(200, json={"ok": True})
        if method == "PUT" and path.startswith("/admin/templates/"):
            body = json.loads(request.content.decode())
            api_state["saved"] = body
            if "{nme}" in body.get("text", "") or body.get("text", "") == "":
                return httpx.Response(400, json={
                    "errors": ["text: неизвестные плейсхолдеры {nme}; разрешены: {name}"],
                    "warnings": [],
                    "leak": SECRET_LEAK,
                })
            key = path.removeprefix("/admin/templates/")
            found = next(
                (item for branch in _branches()["branches"] for item in branch["templates"] if item["key"] == key),
                None,
            )
            updated = dict(found or {"key": key})
            updated["text"] = body.get("text", "")
            if "buttons" in body:
                updated["buttons"] = body["buttons"]
            updated["is_default"] = False
            updated["updated_by"] = body.get("updated_by")
            updated["updated_at"] = "2026-11-13T15:00:00+00:00"
            warnings = []
            for button_id, label in (body.get("buttons") or {}).items():
                if len(label) > 20:
                    warnings.append(
                        f"buttons.{button_id}: {len(label)} символов — MAX рекомендует до 20, "
                        "иначе подпись может обрезаться"
                    )
            return httpx.Response(200, json={"template": updated, "warnings": warnings})
        if method == "POST" and path.endswith("/reset"):
            key = path.removeprefix("/admin/templates/").removesuffix("/reset")
            found = next(
                item for branch in _branches()["branches"] for item in branch["templates"] if item["key"] == key
            )
            updated = dict(found)
            updated["text"] = "Чем могу помочь?"
            updated["buttons"] = {"question": "Вопрос", "review": "Отзыв"}
            updated["is_default"] = True
            updated["updated_by"] = json.loads(request.content.decode()).get("updated_by")
            return httpx.Response(200, json={"template": updated, "warnings": []})
        return httpx.Response(404, json={"error": "not found"})

    def factory(**kwargs):
        kwargs = dict(kwargs)
        kwargs["transport"] = httpx.MockTransport(handler)
        return httpx.AsyncClient(**kwargs)

    monkeypatch.setattr(bot_admin, "_make_client", factory)
    app = FastAPI()
    app.include_router(bot_admin.router)
    with TestClient(app) as test_client:
        yield test_client


def test_preview_and_moscow_time():
    assert bot_admin.preview_text("Привет, {name}! Цена {{100}}", bot_admin.PREVIEW_SAMPLES) == "Привет, Анна! Цена {100}"
    assert bot_admin.format_msk("2026-11-13T14:47:12+00:00") == "13.11.2026 17:47"
    assert len(LONG_REVIEW) == 35
    assert bot_admin._item_platform({}, {}) == "max"
    assert bot_admin._item_platform({"platform": "telegram"}, {}) == "telegram"
    assert bot_admin._item_platform({"channel": "tg"}, {}) == "telegram"
    assert bot_admin._item_platform({}, {"channel": "tg"}) == "telegram"
    assert bot_admin._item_platform({}, {"platform": "max"}) == "max"
    view = bot_admin._inbox_view({
        "id": QUESTION_ID, "kind": "question", "status": "new",
        "payload": {"channel": "tg"}, "text": "hi",
    }, {"question": "❓ Вопрос"})
    assert view["platform"] == "telegram" and view["platform_title"] == "Telegram"


def test_pages_require_auth(client):
    assert client.get("/admin/inbox").status_code == 401
    assert client.get("/admin/templates").status_code == 401
    denied = client.get("/admin/inbox", auth=("admin", "wrong"))
    assert denied.status_code == 401
    assert denied.headers["www-authenticate"].lower().startswith("basic")


def test_missing_token_does_not_call_bot(client, monkeypatch, api_state):
    monkeypatch.delenv("BOT_API_TOKEN", raising=False)
    inbox = client.get("/admin/inbox", auth=AUTH)
    templates = client.get("/admin/templates", auth=AUTH)
    assert inbox.status_code == 200
    assert templates.status_code == 200
    assert "Бот не подключён" in inbox.text
    assert "BOT_API_TOKEN" in inbox.text
    assert "Бот не подключён" in templates.text
    assert api_state["requests"] == []
    assert TOKEN not in inbox.text
    assert "bot.example.test" not in inbox.text


def test_inbox_list_filters_and_hides_secrets(client, api_state):
    page = client.get("/admin/inbox?status=new&kind=question", auth=AUTH)
    assert page.status_code == 200
    assert "❓ Вопрос гостя" in page.text
    assert "Как пройти к водопадам?" in page.text
    assert "<script>alert(1)</script>" not in page.text
    assert "Руфабго понравился" not in page.text
    assert "+7 900 000-00-00" not in page.text
    assert "13.11.2026 17:52" in page.text
    assert page.headers["cache-control"].startswith("no-store")
    assert page.headers["referrer-policy"] == "no-referrer"
    inbox_calls = [request for request in api_state["requests"] if request.url.path == "/inbox"]
    assert inbox_calls
    assert inbox_calls[0].url.params["status"] == "new"
    assert inbox_calls[0].url.params["limit"] == "200"
    assert "kind" not in inbox_calls[0].url.params
    assert inbox_calls[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in page.text
    assert "bot.example.test" not in page.text
    everything = client.get("/admin/inbox", auth=AUTH)
    assert "Рафтинг" in everything.text
    assert "Хочется тихую воду" in everything.text
    assert "Telegram" in everything.text
    assert "Зимой открыт Хаджох?" in everything.text
    assert everything.text.count(">MAX<") >= 1


def test_inbox_detail_and_status_change(client, api_state):
    page = client.get(f"/admin/inbox/{SERVICE_ID}", auth=AUTH)
    assert page.status_code == 200
    assert "Марина" in page.text
    assert "+7 900 000-00-00" in page.text
    assert "Рафтинг" in page.text
    assert "20–22 ноября" in page.text
    assert "podbor_feedback_abc123" in page.text
    assert "https://files.example.test/pic.jpg" in page.text
    assert SECRET_TOKEN not in page.text
    assert "Сохранить статус" in page.text
    assert "id в MAX" in page.text
    assert ">MAX<" in page.text
    tg_page = client.get(f"/admin/inbox/{TG_QUESTION_ID}", auth=AUTH)
    assert tg_page.status_code == 200
    assert "Игорь" in tg_page.text
    assert "id в Telegram" in tg_page.text
    assert "Зимой открыт Хаджох?" in tg_page.text
    assert "id в MAX" not in tg_page.text
    for label in ("Новое", "В работе", "Готово", "Спам"):
        assert label in page.text

    api_state["requests"].clear()
    saved = client.post(
        f"/admin/inbox/{SERVICE_ID}/status",
        data={"status": "done", "back_status": "new", "back_kind": "service_request"},
        auth=AUTH,
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].endswith(
        f"/admin/inbox/{SERVICE_ID}?status=new&kind=service_request&saved=1"
    )
    posted = [request for request in api_state["requests"] if request.method == "POST"]
    assert len(posted) == 1
    assert posted[0].url.path == f"/inbox/{SERVICE_ID}/status"
    assert json.loads(posted[0].content) == {"status": "done"}
    assert "charset=utf-8" in posted[0].headers["content-type"].lower()

    api_state["requests"].clear()
    rejected = client.post(
        f"/admin/inbox/{SERVICE_ID}/status",
        data={"status": "archived"},
        auth=AUTH,
    )
    assert rejected.status_code == 400
    assert "Статус должен быть" in rejected.text
    assert not any(request.method == "POST" for request in api_state["requests"])


def test_unknown_inbox_id(client, api_state):
    missing = client.get("/admin/inbox/not-an-id", auth=AUTH)
    assert missing.status_code == 404
    assert "Обращение не найдено" in missing.text
    assert api_state["requests"] == []


def test_templates_grouped_with_meta_and_button_warning(client):
    page = client.get("/admin/templates", auth=AUTH)
    assert page.status_code == 200
    titles = [
        "Старт и согласие", "Меню", "Вопрос", "Отзыв о месте или маршруте",
        "Заявка на услугу", "Обратная связь по подборщику", "Уведомления админу", "Ошибки и прочее",
    ]
    positions = [page.text.index(title) for title in titles]
    assert positions == sorted(positions)
    assert "Где показывается" in page.text
    assert "Первое сообщение после /start" in page.text
    assert "Плейсхолдеры" in page.text
    assert "{name}" in page.text
    assert "Обязательные" in page.text
    assert "{title}" in page.text
    assert "Анна" in page.text
    assert "13.11.2026 17:47" in page.text
    assert f"buttons.review: {len(LONG_REVIEW)} символов" in page.text
    assert "Сбросить к стандартному" in page.text
    assert 'action="/admin/templates/menu.main/reset"' in page.text
    assert 'action="/admin/templates/question.ask/reset"' not in page.text
    assert "Здравствуйте, Анна!" in page.text
    assert page.headers["cache-control"].startswith("no-store")
    assert TOKEN not in page.text


def test_template_save_validation_and_reset(client, api_state):
    saved = client.post(
        "/admin/templates/start.consent",
        data={"text": "Согласны, {name}?", "button__consent": "Согласна", "button__policy": "Политика", "updated_by": "чужой"},
        auth=AUTH,
    )
    assert saved.status_code == 200
    assert api_state["saved"]["text"] == "Согласны, {name}?"
    assert api_state["saved"]["buttons"] == {"consent": "Согласна", "policy": "Политика"}
    assert api_state["saved"]["updated_by"] == "admin"
    assert "Сохранено" in saved.text
    put = [request for request in api_state["requests"] if request.method == "PUT"]
    assert put[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert "charset=utf-8" in put[0].headers["content-type"].lower()

    invalid = client.post(
        "/admin/templates/question.ask",
        data={"text": "Черновик {nme}"},
        auth=AUTH,
    )
    assert invalid.status_code == 400
    assert "неизвестные плейсхолдеры {nme}" in invalid.text
    assert "Черновик {nme}" in invalid.text
    assert SECRET_LEAK not in invalid.text

    reset = client.post("/admin/templates/menu.main/reset", auth=AUTH)
    assert reset.status_code == 200
    assert "Возвращён стандартный текст" in reset.text
    assert "Чем могу помочь?" in reset.text
    assert 'action="/admin/templates/menu.main/reset"' not in reset.text
    reset_call = [request for request in api_state["requests"] if request.url.path.endswith("/reset")]
    assert json.loads(reset_call[-1].content) == {"updated_by": "admin"}


def test_bot_errors_hide_response_body(client, api_state, caplog):
    caplog.set_level(logging.DEBUG)
    api_state["fail"] = "down"
    down = client.get("/admin/inbox", auth=AUTH)
    assert down.status_code == 200
    assert "Бот временно недоступен" in down.text
    assert SECRET_BODY not in down.text
    assert SECRET_BODY not in caplog.text

    api_state["fail"] = "unauthorized"
    denied = client.get("/admin/templates", auth=AUTH)
    assert "Бот отклонил токен" in denied.text
    assert TOKEN not in denied.text

    api_state["requests"].clear()
    api_state["fail"] = "redirect"
    redirected = client.get("/admin/inbox", auth=AUTH)
    assert "Бот временно недоступен" in redirected.text
    assert "evil.example" not in redirected.text
    assert len(api_state["requests"]) == 1


def test_admin_nav_links_and_database_untouched(monkeypatch):
    admin_html = open("static/admin.html", encoding="utf-8").read()
    assert 'href="/admin/inbox"' in admin_html
    assert "Входящие" in admin_html
    assert 'href="/admin/templates"' in admin_html
    assert "Шаблоны бота" in admin_html

    monkeypatch.delenv("BOT_API_TOKEN", raising=False)

    def explode(**kwargs):
        raise AssertionError("без токена сайт не должен звонить в API бота")

    monkeypatch.setattr(bot_admin, "_make_client", explode)

    from app.database import engine
    from app.main import app

    def snapshot():
        with engine.connect() as conn:
            names = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )).scalars().all()
            counts = {
                name: conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar()
                for name in names
            }
        return sorted(names), counts

    before_names, before_counts = snapshot()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/admin/inbox" in paths
    assert "/admin/templates" in paths
    with TestClient(app) as full:
        assert full.get("/admin/inbox", auth=AUTH).status_code == 200
        assert full.get("/admin/templates", auth=AUTH).status_code == 200
    after_names, after_counts = snapshot()
    assert after_names == before_names
    assert after_counts == before_counts
