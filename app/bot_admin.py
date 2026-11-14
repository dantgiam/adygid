"""Админка бота MAX и Telegram: «Входящие» и «Шаблоны бота».

Сайт ходит в API бота (Yandex Cloud, РФ) только с сервера. Тексты обращений,
имена, телефоны и id — персональные данные: их нельзя писать в базу, файлы,
кэш и логи. Страница запрашивает данные, показывает их и забывает.
"""

import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

# httpx на DEBUG пишет заголовки запроса, а в них bearer-токен.
# Тела ответов тоже не должны попадать в журнал.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_BOT_API_URL = "https://d5dcnh3b6fsskkqbhnvq.emzafcgx.apigw.yandexcloud.net"
BOT_TIMEOUT = 15.0
INBOX_LIMIT = 200
MSK = ZoneInfo("Europe/Moscow")

STATUSES = ("new", "in_progress", "done", "spam")
STATUS_LABELS = {
    "new": "Новое",
    "in_progress": "В работе",
    "done": "Готово",
    "spam": "Спам",
}
STATUS_BADGES = {
    "new": "badge-gold",
    "in_progress": "badge-draft",
    "done": "badge-green",
    "spam": "badge-muted",
}
PLATFORM_LABELS = {
    "max": "MAX",
    "telegram": "Telegram",
}
PLATFORM_BADGES = {
    "max": "badge-max",
    "telegram": "badge-tg",
}
KINDS = ("question", "review", "service_request", "podbor_feedback", "consent_revoked")
# Совпадают с сидом admin.kind_titles. Если API ответил, берём его подписи.
FALLBACK_KIND_TITLES = {
    "question": "❓ Вопрос",
    "review": "⭐ Отзыв о месте/маршруте",
    "service_request": "🧭 Заявка на услугу",
    "podbor_feedback": "🗺 Отзыв о подобранном маршруте",
    "consent_revoked": "⚠️ Отзыв согласия на обработку ПД",
}
BRANCH_TITLES = {
    "start": "Старт и согласие",
    "menu": "Меню",
    "question": "Вопрос",
    "review": "Отзыв о месте или маршруте",
    "service": "Заявка на услугу",
    "podbor": "Обратная связь по подборщику",
    "admin": "Уведомления админу",
    "other": "Ошибки и прочее",
}
TEMPLATE_KIND_LABELS = {
    "message": "сообщение",
    "url": "ссылка",
    "labels": "подписи",
}
BUTTON_HINTS = {
    "consent": "Согласие",
    "policy": "Политика",
    "question": "Вопрос",
    "review": "Отзыв",
    "service": "Заявка",
    "podbor": "Подбор",
    "excursion": "Экскурсия",
    "rafting": "Рафтинг",
    "jeeping": "Джиппинг",
    "other": "Другое",
    "send_phone": "Отправить номер",
    "skip": "Пропустить",
    "cancel": "Отмена",
}
PREVIEW_SAMPLES = {
    "name": "Анна",
    "service": "Рафтинг",
    "policy_url": "https://www.adygid.ru/privacy",
    "title": "❓ Вопрос",
    "user_name": "Анна",
    "user_id": "216290224",
    "details": "Услуга: Рафтинг\nКогда: 20–22 ноября\n",
    "source": "",
    "text": "Текст сообщения",
    "id": "3f0c9a52",
    "kind": "question",
    "when": "20–22 ноября",
    "people": "3 взрослых",
    "phone": "+7 900 000-00-00",
    "start_payload": "podbor_feedback_abc123",
    "count": "5",
}
PROBLEMS = {
    "not_configured": (
        "Бот не подключён",
        "Задайте переменную BOT_API_TOKEN на сервере. Пока её нет, страница ничего "
        "не запрашивает и не падает. Токен и адрес API в браузер не передаются.",
    ),
    "unauthorized": (
        "Бот отклонил токен",
        "Проверьте BOT_API_TOKEN на сервере. Сам токен на странице не показывается.",
    ),
    "unavailable": (
        "Бот временно недоступен",
        "Облако не ответило вовремя. Повторите через минуту — холодный старт иногда занимает несколько секунд.",
    ),
    "error": (
        "Не удалось получить данные",
        "Бот ответил ошибкой. Повторите позже.",
    ),
}

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_BUTTON_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_security = HTTPBasic()
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

TEXT_MAX_DEFAULT = 4000
BUTTON_MAX_DEFAULT = 128
BUTTON_RECOMMENDED_DEFAULT = 20


class BotNotConfigured(Exception):
    pass


class BotApiError(Exception):
    """Ошибка API без тела ответа: в текст исключения персональные данные не попадают."""

    def __init__(self, status: int, *, unavailable: bool = False, errors=None, warnings=None, message: str = ""):
        super().__init__("bot api unavailable" if unavailable else f"bot api {status}")
        self.status = status
        self.unavailable = unavailable
        self.errors = [_clip(item, 500) for item in (errors or []) if isinstance(item, str) and item.strip()]
        self.warnings = [_clip(item, 500) for item in (warnings or []) if isinstance(item, str) and item.strip()]
        self.message = _clip(message, 300) if isinstance(message, str) else ""


def _clip(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _make_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(**kwargs)


def bot_settings() -> tuple[str, str]:
    token = os.environ.get("BOT_API_TOKEN", "").strip()
    base = os.environ.get("BOT_API_URL", DEFAULT_BOT_API_URL).strip().rstrip("/") or DEFAULT_BOT_API_URL
    return token, base


async def bot_api(method: str, path: str, *, params=None, json_body=None) -> dict:
    token, base = bot_settings()
    if not token:
        raise BotNotConfigured()
    if not path.startswith("/"):
        path = "/" + path
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    kwargs = {"params": params or None}
    if json_body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        kwargs["content"] = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    try:
        async with _make_client(
            base_url=base,
            headers=headers,
            timeout=BOT_TIMEOUT,
            follow_redirects=False,
        ) as client:
            response = await client.request(method, path, **kwargs)
            await response.aread()
    except httpx.HTTPError:
        raise BotApiError(0, unavailable=True) from None
    if response.status_code >= 500 or not (200 <= response.status_code < 300):
        # 3xx не преследуем: follow_redirects выключен, чтобы токен не ушёл на другой хост.
        # Тело 5xx не разбираем — там может быть текст обращения.
        if response.status_code >= 500 or response.status_code < 400:
            raise BotApiError(response.status_code, unavailable=True)
        data = _json_dict(response)
        errors = data.get("errors") if isinstance(data.get("errors"), list) else []
        warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
        message = data.get("error") if isinstance(data.get("error"), str) else ""
        raise BotApiError(
            response.status_code,
            unavailable=False,
            errors=errors,
            warnings=warnings,
            message=message,
        )
    return _json_dict(response)


def _json_dict(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def require_bot_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """Тот же HTTP Basic, что у /admin: ADMIN_USER и ADMIN_PASSWORD."""
    user = os.getenv("ADMIN_USER", "admin")
    password = os.getenv("ADMIN_PASSWORD", "adygid")
    ok_user = secrets.compare_digest(credentials.username, user)
    ok_pass = secrets.compare_digest(credentials.password, password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def format_msk(value) -> str:
    if not value or not isinstance(value, str):
        return "—"
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


def preview_text(text: str, samples: dict) -> str:
    """Подставляет примеры плейсхолдеров. {{ и }} остаются буквальными скобками."""
    if not text:
        return ""
    left, right = "\x00", "\x01"
    protected = text.replace("{{", left).replace("}}", right)

    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key in samples and samples[key] is not None:
            return str(samples[key])
        return match.group(0)

    rendered = _PLACEHOLDER_RE.sub(repl, protected)
    return rendered.replace(left, "{").replace(right, "}")


def _page(template_name: str, context: dict, status_code: int = 200):
    response = templates.TemplateResponse(
        context["request"], template_name, context, status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


def _problem(request: Request, section: str, code: str, status_code: int = 200):
    title, text = PROBLEMS.get(code, PROBLEMS["error"])
    return _page(
        "bot_problem.html",
        {"request": request, "section": section, "problem_title": title, "problem_text": text},
        status_code=status_code,
    )


def _problem_from(request: Request, section: str, exc: Exception):
    if isinstance(exc, BotNotConfigured):
        return _problem(request, section, "not_configured")
    if isinstance(exc, BotApiError):
        if exc.status == 401:
            return _problem(request, section, "unauthorized")
        if exc.unavailable:
            return _problem(request, section, "unavailable")
        return _problem(request, section, "error")
    return _problem(request, section, "error")


def _clean_status(value: str | None) -> str | None:
    return value if value in STATUSES else None


def _clean_kind(value: str | None) -> str | None:
    return value if value in KINDS else None


def _valid_key(key: str) -> bool:
    return bool(_KEY_RE.fullmatch(key or ""))


def _valid_id(item_id: str) -> bool:
    return bool(_UUID_RE.fullmatch(item_id or ""))


def _query(status: str | None, kind: str | None, **extra) -> str:
    pairs = {}
    if status:
        pairs["status"] = status
    if kind:
        pairs["kind"] = kind
    for key, value in extra.items():
        if value:
            pairs[key] = value
    return urlencode(pairs)


def _preview_line(text, payload: dict) -> str:
    if isinstance(text, str) and text.strip():
        line = " ".join(text.split())
    else:
        bits = []
        if payload.get("service"):
            bits.append(str(payload["service"]))
        if isinstance(payload.get("comment"), str) and payload["comment"].strip():
            bits.append(" ".join(payload["comment"].split()))
        elif payload.get("when"):
            bits.append(str(payload["when"]))
        line = " · ".join(bits) if bits else "Без текста"
    if len(line) > 160:
        return line[:159] + "…"
    return line


def _attachments(payload: dict) -> list[dict]:
    found = []
    raw = payload.get("attachments")
    if not isinstance(raw, list):
        return found
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        kind = item.get("type") if isinstance(item.get("type"), str) else "file"
        found.append({"type": kind, "url": url})
    return found



def _item_platform(raw: dict, payload: dict) -> str:
    """max | telegram. Берём API-поле platform, иначе channel / payload, иначе max."""
    value = None
    if isinstance(raw, dict):
        value = raw.get("platform") or raw.get("channel")
    if value is None and isinstance(payload, dict):
        value = payload.get("platform") or payload.get("channel")
    raw_value = str(value or "max").strip().lower()
    if raw_value in ("tg", "telegram"):
        return "telegram"
    return "max"


def _inbox_view(raw: dict, titles: dict) -> dict | None:
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not _valid_id(item_id):
        return None
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    kind = raw.get("kind") if isinstance(raw.get("kind"), str) else ""
    status = raw.get("status") if isinstance(raw.get("status"), str) else ""
    text = raw.get("text") if isinstance(raw.get("text"), str) else None
    platform = _item_platform(raw, payload)
    return {
        "id": item_id,
        "short_id": item_id[:8],
        "created_at": format_msk(raw.get("created_at")),
        "updated_at": format_msk(raw.get("updated_at")),
        "user_id": raw.get("user_id") if raw.get("user_id") is not None else "—",
        "user_name": raw.get("user_name") if isinstance(raw.get("user_name"), str) and raw.get("user_name").strip() else "Без имени",
        "kind": kind,
        "kind_title": titles.get(kind) or FALLBACK_KIND_TITLES.get(kind) or (kind or "Обращение"),
        "text": text,
        "status": status,
        "status_title": STATUS_LABELS.get(status, status or "—"),
        "status_badge": STATUS_BADGES.get(status, ""),
        "notified": bool(raw.get("notified")),
        "service": _text_or_none(payload.get("service")),
        "when": _text_or_none(payload.get("when")),
        "people": _text_or_none(payload.get("people")),
        "phone": _text_or_none(payload.get("phone")),
        "comment": _text_or_none(payload.get("comment")),
        "start_payload": _text_or_none(payload.get("start_payload")),
        "free_text": bool(payload.get("free_text")),
        "attachments": _attachments(payload),
        "preview": _preview_line(text, payload),
        "platform": platform,
        "platform_title": PLATFORM_LABELS.get(platform, "MAX"),
        "platform_badge": PLATFORM_BADGES.get(platform, "badge-max"),
    }


def _text_or_none(value):
    if isinstance(value, str) and value.strip():
        return value
    return None


async def _kind_titles() -> dict:
    titles = dict(FALLBACK_KIND_TITLES)
    try:
        data = await bot_api("GET", "/admin/templates/admin.kind_titles")
    except (BotNotConfigured, BotApiError):
        return titles
    template = data.get("template") if isinstance(data.get("template"), dict) else {}
    buttons = template.get("buttons") if isinstance(template.get("buttons"), dict) else {}
    for key, value in buttons.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            titles[key] = value
    return titles


async def _load_inbox(status: str | None) -> tuple[list[dict], bool]:
    params = {"limit": INBOX_LIMIT}
    if status:
        params["status"] = status
    data = await bot_api("GET", "/inbox", params=params)
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    return raw_items, len(raw_items) >= INBOX_LIMIT


def _filter_items(raw_items: list, titles: dict, kind: str | None) -> list[dict]:
    views = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        if kind and raw.get("kind") != kind:
            continue
        view = _inbox_view(raw, titles)
        if view:
            views.append(view)
    return views


def _button_notes(buttons: dict, limits: dict) -> tuple[list[str], list[str]]:
    recommended = int(limits.get("button_recommended") or BUTTON_RECOMMENDED_DEFAULT)
    hard = int(limits.get("button_max") or BUTTON_MAX_DEFAULT)
    warnings = []
    errors = []
    for button_id, label in buttons.items():
        length = len(label or "")
        if length > hard:
            errors.append(f"buttons.{button_id}: {length} символов — лимит MAX {hard}")
        elif length > recommended:
            warnings.append(
                f"buttons.{button_id}: {length} символов — MAX рекомендует до {recommended}, "
                "иначе подпись может обрезаться"
            )
    return warnings, errors


def _policy_url(branches: list[dict]) -> str:
    for branch in branches:
        for template in branch.get("templates") or []:
            if template.get("key") == "start.policy_url" and isinstance(template.get("text"), str):
                text = template["text"].strip()
                if text.startswith("https://"):
                    return text
    return PREVIEW_SAMPLES["policy_url"]


def _template_view(raw: dict, samples: dict, focus: dict | None) -> dict:
    key = raw.get("key") if isinstance(raw.get("key"), str) else ""
    buttons = raw.get("buttons") if isinstance(raw.get("buttons"), dict) else None
    text = raw.get("text") if isinstance(raw.get("text"), str) else ""
    # Черновик подменяем только после ошибки валидации. Успешное сохранение
    # уже лежит в raw, и пустой focus не должен затирать текст.
    if focus and focus.get("key") == key and focus.get("keep_draft"):
        if isinstance(focus.get("text"), str):
            text = focus["text"]
        if isinstance(focus.get("buttons"), dict):
            buttons = dict(buttons or {})
            for button_id, label in focus["buttons"].items():
                buttons[button_id] = label if isinstance(label, str) else ""
    limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
    limits = {
        "text_max": int(limits.get("text_max") or TEXT_MAX_DEFAULT),
        "button_max": int(limits.get("button_max") or BUTTON_MAX_DEFAULT),
        "button_recommended": int(limits.get("button_recommended") or BUTTON_RECOMMENDED_DEFAULT),
    }
    button_rows = []
    button_map = buttons or {}
    for button_id, label in button_map.items():
        if not isinstance(button_id, str) or not _BUTTON_ID_RE.fullmatch(button_id):
            continue
        label_text = label if isinstance(label, str) else ""
        length = len(label_text)
        if length > limits["button_max"]:
            tone = "bad"
        elif length > limits["button_recommended"]:
            tone = "warn"
        else:
            tone = ""
        button_rows.append({
            "id": button_id,
            "label": label_text,
            "hint": BUTTON_HINTS.get(button_id, ""),
            "length": length,
            "tone": tone,
        })
    local_warnings, local_errors = _button_notes(
        {row["id"]: row["label"] for row in button_rows},
        limits,
    )
    api_errors = []
    api_warnings = []
    saved = False
    reset_done = False
    if focus and focus.get("key") == key:
        api_errors = list(focus.get("errors") or [])
        api_warnings = [item for item in (focus.get("warnings") or []) if item not in local_warnings]
        saved = bool(focus.get("saved"))
        reset_done = bool(focus.get("reset"))
    kind = raw.get("kind") if raw.get("kind") in TEMPLATE_KIND_LABELS else "message"
    placeholders = [item for item in (raw.get("placeholders") or []) if isinstance(item, str)]
    required = [item for item in (raw.get("required_placeholders") or []) if isinstance(item, str)]
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    updated_by = raw.get("updated_by") if isinstance(raw.get("updated_by"), str) else ""
    return {
        "key": key,
        "title": raw.get("title") if isinstance(raw.get("title"), str) and raw.get("title") else key,
        "description": description,
        "kind": kind,
        "kind_label": TEMPLATE_KIND_LABELS.get(kind, kind),
        "text": text,
        "text_length": len(text),
        "text_rows": min(14, max(4, text.count("\n") + 2)),
        "buttons": button_rows,
        "placeholders": placeholders,
        "required_placeholders": required,
        "is_default": bool(raw.get("is_default")),
        "updated_at": format_msk(raw.get("updated_at")),
        "updated_by": updated_by or "—",
        "limits": limits,
        "preview": preview_text(text, samples),
        "local_warnings": local_warnings,
        "local_errors": local_errors,
        "api_errors": api_errors,
        "api_warnings": api_warnings,
        "saved": saved,
        "reset_done": reset_done,
        "focused": bool(focus and focus.get("key") == key),
    }


def _branches_view(data: dict, focus: dict | None) -> tuple[list[dict], dict]:
    raw_branches = data.get("branches") if isinstance(data.get("branches"), list) else []
    samples = dict(PREVIEW_SAMPLES)
    samples["policy_url"] = _policy_url(raw_branches)
    branches = []
    for raw in raw_branches:
        if not isinstance(raw, dict):
            continue
        code = raw.get("branch") if isinstance(raw.get("branch"), str) else ""
        title = raw.get("title") if isinstance(raw.get("title"), str) and raw.get("title").strip() else BRANCH_TITLES.get(code, code)
        cards = []
        for item in raw.get("templates") or []:
            if isinstance(item, dict) and isinstance(item.get("key"), str):
                cards.append(_template_view(item, samples, focus))
        if code or cards:
            branches.append({"branch": code or "other", "title": title, "templates": cards})
    return branches, samples


async def _load_templates() -> dict:
    return await bot_api("GET", "/admin/templates")


def _known_buttons(data: dict, key: str) -> list[str]:
    for branch in data.get("branches") or []:
        if not isinstance(branch, dict):
            continue
        for item in branch.get("templates") or []:
            if isinstance(item, dict) and item.get("key") == key:
                buttons = item.get("buttons") if isinstance(item.get("buttons"), dict) else {}
                defaults = item.get("default_buttons") if isinstance(item.get("default_buttons"), dict) else {}
                ordered = []
                for button_id in list(buttons) + list(defaults):
                    if isinstance(button_id, str) and _BUTTON_ID_RE.fullmatch(button_id) and button_id not in ordered:
                        ordered.append(button_id)
                return ordered
    return []


def _replace_template(data: dict, updated: dict) -> dict:
    key = updated.get("key")
    branches = []
    for branch in data.get("branches") or []:
        if not isinstance(branch, dict):
            branches.append(branch)
            continue
        cards = []
        for item in branch.get("templates") or []:
            if isinstance(item, dict) and item.get("key") == key and isinstance(updated, dict):
                cards.append(updated)
            else:
                cards.append(item)
        copied = dict(branch)
        copied["templates"] = cards
        branches.append(copied)
    return {"branches": branches}


async def _editor_username(username: str) -> str:
    cleaned = " ".join(username.split())
    return _clip(cleaned, 80) or "admin"


@router.get("/admin/inbox")
async def inbox_list(
    request: Request,
    status: str | None = None,
    kind: str | None = None,
    _: str = Depends(require_bot_admin),
):
    status = _clean_status(status)
    kind = _clean_kind(kind)
    try:
        raw_items, truncated = await _load_inbox(status)
        titles = await _kind_titles()
    except (BotNotConfigured, BotApiError) as exc:
        return _problem_from(request, "inbox", exc)
    items = _filter_items(raw_items, titles, kind)
    kind_options = [(code, titles.get(code) or FALLBACK_KIND_TITLES.get(code, code)) for code in KINDS]
    return _page(
        "bot_inbox.html",
        {
            "request": request,
            "section": "inbox",
            "items": items,
            "status": status or "",
            "kind": kind or "",
            "statuses": [(code, STATUS_LABELS[code]) for code in STATUSES],
            "kinds": kind_options,
            "truncated": truncated,
            "list_query": _query(status, kind),
        },
    )


@router.get("/admin/inbox/{item_id}")
async def inbox_detail(
    request: Request,
    item_id: str,
    status: str | None = None,
    kind: str | None = None,
    saved: str | None = None,
    _: str = Depends(require_bot_admin),
):
    status = _clean_status(status)
    kind = _clean_kind(kind)
    if not _valid_id(item_id):
        return _page(
            "bot_inbox_detail.html",
            _detail_context(request, None, status, kind, missing=True),
            status_code=404,
        )
    try:
        raw_items, _truncated = await _load_inbox(None)
        titles = await _kind_titles()
    except (BotNotConfigured, BotApiError) as exc:
        return _problem_from(request, "inbox", exc)
    found = next((item for item in _filter_items(raw_items, titles, None) if item["id"] == item_id), None)
    return _page(
        "bot_inbox_detail.html",
        _detail_context(request, found, status, kind, saved=saved == "1", missing=found is None),
        status_code=200 if found else 404,
    )


def _detail_context(request, item, status, kind, saved=False, missing=False, error=""):
    return {
        "request": request,
        "section": "inbox",
        "item": item,
        "missing": missing,
        "saved": saved,
        "error": error,
        "statuses": [(code, STATUS_LABELS[code]) for code in STATUSES],
        "list_query": _query(status, kind),
        "back_status": status or "",
        "back_kind": kind or "",
    }


@router.post("/admin/inbox/{item_id}/status")
async def inbox_status(
    request: Request,
    item_id: str,
    username: str = Depends(require_bot_admin),
):
    del username  # статус меняет сам факт входа, имя в API статуса не передаётся
    form = await request.form()
    status_filter = _clean_status(_form_str(form, "back_status"))
    kind_filter = _clean_kind(_form_str(form, "back_kind"))
    new_status = _form_str(form, "status")
    if not _valid_id(item_id):
        return _page(
            "bot_inbox_detail.html",
            _detail_context(request, None, status_filter, kind_filter, missing=True, error="Некорректный номер обращения"),
            status_code=404,
        )
    if new_status not in STATUSES:
        item, error_page = await _detail_or_problem(request, item_id, status_filter, kind_filter)
        if error_page is not None:
            return error_page
        context = _detail_context(
            request, item, status_filter, kind_filter, error="Статус должен быть одним из: новое, в работе, готово, спам",
        )
        return _page("bot_inbox_detail.html", context, status_code=400)
    try:
        await bot_api("POST", f"/inbox/{item_id}/status", json_body={"status": new_status})
    except (BotNotConfigured, BotApiError) as exc:
        if isinstance(exc, BotApiError) and not exc.unavailable and exc.status != 401:
            item, error_page = await _detail_or_problem(request, item_id, status_filter, kind_filter)
            if error_page is not None:
                return error_page
            message = exc.message or "Бот не принял статус"
            return _page(
                "bot_inbox_detail.html",
                _detail_context(request, item, status_filter, kind_filter, error=message),
                status_code=exc.status or 400,
            )
        return _problem_from(request, "inbox", exc)
    target = f"/admin/inbox/{item_id}"
    query = _query(status_filter, kind_filter, saved="1")
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(target, status_code=303)


async def _detail_or_problem(request, item_id, status, kind):
    try:
        raw_items, _truncated = await _load_inbox(None)
        titles = await _kind_titles()
    except (BotNotConfigured, BotApiError) as exc:
        return None, _problem_from(request, "inbox", exc)
    found = next((item for item in _filter_items(raw_items, titles, None) if item["id"] == item_id), None)
    return found, None


def _form_str(form, name: str) -> str:
    value = form.get(name)
    if value is None:
        return ""
    return str(value)


@router.get("/admin/templates")
async def template_list(request: Request, _: str = Depends(require_bot_admin)):
    try:
        data = await _load_templates()
    except (BotNotConfigured, BotApiError) as exc:
        return _problem_from(request, "templates", exc)
    branches, samples = _branches_view(data, None)
    return _page(
        "bot_templates.html",
        {"request": request, "section": "templates", "branches": branches, "samples": samples},
    )


@router.post("/admin/templates/{key}")
async def template_save(request: Request, key: str, username: str = Depends(require_bot_admin)):
    if not _valid_key(key):
        return _problem(request, "templates", "error", status_code=404)
    form = await request.form()
    text = _form_str(form, "text")
    try:
        current = await _load_templates()
    except (BotNotConfigured, BotApiError) as exc:
        return _problem_from(request, "templates", exc)
    button_ids = _known_buttons(current, key)
    if not button_ids and not any(
        isinstance(item, dict) and item.get("key") == key
        for branch in current.get("branches") or []
        if isinstance(branch, dict)
        for item in branch.get("templates") or []
    ):
        return _problem(request, "templates", "error", status_code=404)
    buttons = {button_id: _form_str(form, f"button__{button_id}") for button_id in button_ids}
    body = {"text": text, "updated_by": await _editor_username(username)}
    if button_ids:
        body["buttons"] = buttons
    focus = {
        "key": key,
        "text": text,
        "buttons": buttons or None,
        "errors": [],
        "warnings": [],
        "saved": False,
        "keep_draft": False,
    }
    try:
        saved = await bot_api("PUT", f"/admin/templates/{key}", json_body=body)
    except BotApiError as exc:
        if exc.unavailable or exc.status == 401:
            return _problem_from(request, "templates", exc)
        if exc.status == 404:
            return _problem(request, "templates", "error", status_code=404)
        focus["keep_draft"] = True
        focus["errors"] = exc.errors or ([exc.message] if exc.message else ["Бот не принял шаблон"])
        focus["warnings"] = exc.warnings
        branches, samples = _branches_view(current, focus)
        return _page(
            "bot_templates.html",
            {"request": request, "section": "templates", "branches": branches, "samples": samples},
            status_code=400,
        )
    except BotNotConfigured as exc:
        return _problem_from(request, "templates", exc)
    updated = saved.get("template") if isinstance(saved.get("template"), dict) else None
    merged = _replace_template(current, updated) if updated else current
    focus["saved"] = True
    focus["warnings"] = saved.get("warnings") if isinstance(saved.get("warnings"), list) else []
    focus["text"] = updated.get("text") if updated and isinstance(updated.get("text"), str) else text
    if updated and isinstance(updated.get("buttons"), dict):
        focus["buttons"] = updated["buttons"]
    branches, samples = _branches_view(merged, focus)
    return _page(
        "bot_templates.html",
        {"request": request, "section": "templates", "branches": branches, "samples": samples},
    )


@router.post("/admin/templates/{key}/reset")
async def template_reset(request: Request, key: str, username: str = Depends(require_bot_admin)):
    if not _valid_key(key):
        return _problem(request, "templates", "error", status_code=404)
    try:
        current = await _load_templates()
        saved = await bot_api(
            "POST",
            f"/admin/templates/{key}/reset",
            json_body={"updated_by": await _editor_username(username)},
        )
    except (BotNotConfigured, BotApiError) as exc:
        if isinstance(exc, BotApiError) and not exc.unavailable and exc.status not in (401, 404, 0):
            focus = {
                "key": key,
                "errors": exc.errors or ([exc.message] if exc.message else ["Не удалось вернуть стандартный текст"]),
                "warnings": exc.warnings,
            }
            try:
                current = await _load_templates()
            except (BotNotConfigured, BotApiError):
                return _problem_from(request, "templates", exc)
            branches, samples = _branches_view(current, focus)
            return _page(
                "bot_templates.html",
                {"request": request, "section": "templates", "branches": branches, "samples": samples},
                status_code=exc.status or 400,
            )
        return _problem_from(request, "templates", exc)
    updated = saved.get("template") if isinstance(saved.get("template"), dict) else None
    merged = _replace_template(current, updated) if updated else current
    focus = {
        "key": key,
        "errors": [],
        "warnings": saved.get("warnings") if isinstance(saved.get("warnings"), list) else [],
        "reset": True,
    }
    branches, samples = _branches_view(merged, focus)
    return _page(
        "bot_templates.html",
        {"request": request, "section": "templates", "branches": branches, "samples": samples},
    )
