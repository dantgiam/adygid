"""«Коротко для поездки» и поисковый сниппет карточек мест — из базы.

Источник правды — таблица place_trip_blocks (правится в админке
/admin/texts/places). Словарь seo.PLACE_PRACTICAL остаётся только начальным
наполнением: при первом старте после выкладки каждая его запись один раз
копируется в базу (ON CONFLICT DO NOTHING — правки из админки не
перезаписываются). Если записи в базе нет или база недоступна, карточка
рисуется по-старому, из кода, — поэтому до и после выкладки сайт выглядит
одинаково.

Блок в базе:
  rows: [{key, label, text, verified, checked_on, source_url, ld}]
    key — hours/tickets/cash/how/visit/winter/kids/pets или custom;
    verified — «проверено по официальному источнику»;
    ld — поля для поисковика у проверенной строки:
      hours:   short, opens, closes, days[], hours_place, spec[]
      tickets: price, label, place
      cash:    cash_only
      pets:    allowed
  search_facts: {locality, street, phone} — адрес и телефон в разметке;
  sources: [{title, url}] — «Проверено … · источники» под таблицей.

В JSON-LD, в title и description попадает только то, что стоит в строках
с отметкой «проверено». Нет проверенных строк — нет и фактов.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from datetime import date
from typing import Optional

from sqlalchemy import text

from site_app import seo

log = logging.getLogger("adygid.trip_facts")

STANDARD_KEYS = [k for k, _ in seo.PRACTICAL_LABELS if k != "combine"]
LABELS = dict(seo.PRACTICAL_LABELS)
# Строки, после которых в таблице встаёт автоматическое «Время посещения».
_BEFORE_VISIT = {"hours", "tickets", "cash", "how"}
COMBINE_LABEL = LABELS["combine"]

_CACHE: dict = {"blocks": None, "at": 0.0}
_CACHE_TTL_S = 30
_LOCK = threading.Lock()


# ───────────────── из кода (seo.PLACE_PRACTICAL) в формат базы ─────────────────

def block_from_code(place_id: int) -> Optional[dict]:
    """Запись seo.PLACE_PRACTICAL / PLACE_TITLES в формате базы или None."""
    cfg = seo.PLACE_PRACTICAL.get(place_id)
    title = seo.PLACE_TITLES.get(place_id)
    if cfg is None and title is None:
        return None
    cfg = cfg or {}
    f = cfg.get("facts") or {}
    checked = cfg.get("checked") or ""
    rows = []
    for key in STANDARD_KEYS:
        v = cfg.get(key)
        if not v:
            continue
        if isinstance(v, dict):
            txt, src = v["text"], v.get("source") or ""
        else:
            txt, src = v, ""
        ld: dict = {}
        verified = False
        if f:
            if key == "hours" and f.get("hours"):
                verified = True
                ld = {"short": f["hours"]}
                for k_ld, k_f in (("opens", "opens"), ("closes", "closes"), ("days", "days"),
                                  ("hours_place", "hours_place"), ("spec", "hours_spec")):
                    if f.get(k_f):
                        ld[k_ld] = copy.deepcopy(f[k_f])
            elif key == "tickets" and f.get("price") is not None:
                verified = True
                ld = {"price": f["price"], "label": f.get("price_label") or "", "place": f.get("price_place") or ""}
            elif key == "cash" and f.get("cash_only"):
                verified = True
                ld = {"cash_only": True}
            elif key == "pets" and f.get("pets") is not None:
                verified = True
                ld = {"allowed": bool(f["pets"])}
        rows.append({"key": key, "label": LABELS[key], "text": txt, "verified": verified,
                     "checked_on": checked if verified else "", "source_url": src, "ld": ld})
    seo_title = f.get("seo_title") or (title if not f.get("hours") else None)
    return {
        "place_id": place_id,
        "enabled": bool(cfg),
        "heading_name": f.get("name") or "",
        "seo_title": seo_title or "",
        "seo_description": "",
        "rows": rows,
        "combine_ids": list(cfg.get("combine") or []),
        "route_id": cfg.get("route"),
        "auto_visit": True,
        "search_facts": {k: f[k] for k in ("locality", "street", "phone") if f.get(k)},
        "sources": [dict(seo.FACT_SOURCES[k]) for k in cfg.get("sources", [])],
        "updated_at": None,
        "updated_by": None,
        "from_code": True,
    }


def code_place_ids() -> list:
    return sorted(set(seo.PLACE_PRACTICAL) | set(seo.PLACE_TITLES))


# ───────────────── чтение из базы с кэшем ─────────────────

_COLUMNS = ("place_id", "enabled", "heading_name", "seo_title", "seo_description", "rows",
            "combine_ids", "route_id", "auto_visit", "search_facts", "sources", "updated_at", "updated_by")


def _row_to_block(r) -> dict:
    b = dict(zip(_COLUMNS, r))
    for k in ("heading_name", "seo_title", "seo_description"):
        b[k] = b[k] or ""
    b["rows"] = b["rows"] or []
    b["combine_ids"] = b["combine_ids"] or []
    b["search_facts"] = b["search_facts"] or {}
    b["sources"] = b["sources"] or []
    b["from_code"] = False
    return b


def _load_all() -> dict:
    from app.database import engine
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {', '.join(_COLUMNS)} FROM place_trip_blocks")).all()
    except Exception:
        log.exception("place_trip_blocks unavailable — карточки из кода")
        return {}
    return {r[0]: _row_to_block(r) for r in rows}


def all_blocks() -> dict:
    now = time.monotonic()
    with _LOCK:
        if _CACHE["blocks"] is not None and now - _CACHE["at"] < _CACHE_TTL_S:
            return _CACHE["blocks"]
    blocks = _load_all()
    with _LOCK:
        _CACHE["blocks"], _CACHE["at"] = blocks, time.monotonic()
    return blocks


def invalidate() -> None:
    with _LOCK:
        _CACHE["blocks"] = None


def block_for(place_id: Optional[int]) -> Optional[dict]:
    """Блок карточки: из базы, а если записи нет — из кода."""
    if place_id is None:
        return None
    b = all_blocks().get(place_id)
    if b is not None:
        return b
    return block_from_code(place_id)


# ───────────────── что из блока видит сайт ─────────────────

def _verified(block: dict, key: str) -> Optional[dict]:
    for r in block.get("rows") or []:
        if r.get("key") == key and r.get("verified"):
            return r
    return None


def facts(block: Optional[dict], name: str = "") -> Optional[dict]:
    """Проверенные факты в формате seo (name, hours, opens, price…) или None."""
    if not block or not any(r.get("verified") for r in block.get("rows") or []):
        return None
    f: dict = {"name": block.get("heading_name") or name}
    h = _verified(block, "hours")
    if h:
        ld = h.get("ld") or {}
        f["hours"] = ld.get("short") or h.get("text") or ""
        for k_ld, k_f in (("opens", "opens"), ("closes", "closes"), ("days", "days"),
                          ("hours_place", "hours_place"), ("spec", "hours_spec")):
            if ld.get(k_ld):
                f[k_f] = ld[k_ld]
    for k in ("locality", "street", "phone"):
        v = (block.get("search_facts") or {}).get(k)
        if v:
            f[k] = v
    t = _verified(block, "tickets")
    if t:
        ld = t.get("ld") or {}
        if ld.get("price") not in (None, ""):
            f["price"] = int(ld["price"])
            if ld.get("label"):
                f["price_label"] = ld["label"]
            if ld.get("place"):
                f["price_place"] = ld["place"]
    c = _verified(block, "cash")
    if c and (c.get("ld") or {}).get("cash_only"):
        f["cash_only"] = True
    p = _verified(block, "pets")
    if p and (p.get("ld") or {}).get("allowed") is not None:
        f["pets"] = bool(p["ld"]["allowed"])
    return f


def checked(block: Optional[dict]) -> Optional[dict]:
    """«Проверено <дата> · источники»: самая свежая дата проверенных строк."""
    if not block:
        return None
    dates = [r["checked_on"] for r in block.get("rows") or [] if r.get("verified") and r.get("checked_on")]
    if not dates:
        return None
    return seo.checked_info(max(dates), block.get("sources") or [])


def heading(block: Optional[dict], name: str) -> str:
    return seo.heading_from_facts(facts(block, name), name)


def auto_title(block: Optional[dict], name: str, district: Optional[str]) -> str:
    """Title без ручной правки: из фактов или по общему правилу."""
    return seo.title_from_facts(facts(block, name), name) or seo.generic_place_title(name, district)


def title(block: Optional[dict], name: str, district: Optional[str]) -> str:
    if block and block.get("seo_title"):
        return block["seo_title"]
    return auto_title(block, name, district)


def auto_description(block: Optional[dict], name: str) -> Optional[str]:
    return seo.description_from_facts(facts(block, name), checked(block), name)


def description(block: Optional[dict], name: str) -> Optional[str]:
    if block and block.get("seo_description"):
        return block["seo_description"]
    return auto_description(block, name)


def price_label(block: Optional[dict], name: str = "") -> Optional[str]:
    f = facts(block, name) or {}
    label = f.get("price_label")
    if f.get("price") is None or not label:
        return None
    return label[:1].upper() + label[1:]


def table_rows(block: Optional[dict], *, visit_auto: Optional[str], combine_links: list) -> list:
    """Строки таблицы для шаблона: [{key, label, text, source?} | {key, label, links}]."""
    if not block or not block.get("enabled"):
        return []
    out = []
    for r in block.get("rows") or []:
        txt = (r.get("text") or "").strip()
        if not txt:
            continue
        key = r.get("key") if r.get("key") in LABELS else "custom"
        row = {"key": key, "label": r.get("label") or LABELS.get(key, ""), "text": txt}
        if r.get("source_url"):
            row["source"] = r["source_url"]
        out.append(row)
    if block.get("auto_visit", True) and visit_auto and not any(r["key"] == "visit" for r in out):
        pos = 0
        for i, r in enumerate(out):
            if r["key"] in _BEFORE_VISIT:
                pos = i + 1
        out.insert(pos, {"key": "visit", "label": LABELS["visit"], "text": visit_auto})
    if combine_links:
        out.append({"key": "combine", "label": COMBINE_LABEL, "links": combine_links})
    return out


# ───────────────── начальное наполнение ─────────────────

def seed_from_code(conn) -> int:
    """Копирует записи из кода в базу один раз. Существующие не трогает."""
    import json
    n = 0
    for pid in code_place_ids():
        b = block_from_code(pid)
        res = conn.execute(text(
            "INSERT INTO place_trip_blocks (place_id, enabled, heading_name, seo_title, seo_description, rows, "
            "combine_ids, route_id, auto_visit, search_facts, sources, updated_at, updated_by) "
            "VALUES (:pid, :enabled, :hn, :st, NULL, CAST(:rows AS jsonb), CAST(:comb AS jsonb), :route, TRUE, "
            "CAST(:sf AS jsonb), CAST(:src AS jsonb), now(), 'перенос из кода') "
            "ON CONFLICT (place_id) DO NOTHING"
        ), {"pid": pid, "enabled": b["enabled"], "hn": b["heading_name"] or None, "st": b["seo_title"] or None,
            "rows": json.dumps(b["rows"], ensure_ascii=False), "comb": json.dumps(b["combine_ids"]),
            "route": b["route_id"], "sf": json.dumps(b["search_facts"], ensure_ascii=False),
            "src": json.dumps(b["sources"], ensure_ascii=False)})
        n += res.rowcount or 0
    return n


def today_iso() -> str:
    return date.today().isoformat()
