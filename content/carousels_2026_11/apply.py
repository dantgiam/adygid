"""Вставка лент в сохранённый HTML. Базу не открывает.

Лента — несколько `<figure class="shot">` подряд. На сайте они
собираются в карусель с заглядыванием следующего кадра. Между
фигурами только перевод строки, иначе рендер их разделит.

Повторный запуск видит метку `adygid-carousel:` и ничего не дублирует.
SQL обновляет строку только если текст всё ещё совпадает со снимком.
"""
from __future__ import annotations

import hashlib
import json
import re
from html import escape
from pathlib import Path

from content.carousels_2026_11.plan import PLAN, SKIP_PLACE_IDS

ROOT = Path(__file__).resolve().parent
BEFORE = ROOT / "before.json"
PLACES = ROOT / "places.json"

_HEADING_RE = re.compile(r"<h([23])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_UPLOAD_RE = re.compile(r"/uploads/([A-Za-z0-9]+)")


def body_md5(html: str) -> str:
    return hashlib.md5(html.encode("utf-8")).hexdigest()


def _plain(html: str) -> str:
    return " ".join(_TAG_RE.sub(" ", html or "").split())


def _split_caption(raw: str, place_name: str) -> tuple[str, str]:
    text = _plain(raw)
    if "Фото:" in text:
        left, right = text.split("Фото:", 1)
        caption = left.strip(" .—-") or place_name
        credit = "Фото: " + " ".join(right.split())
        return caption, credit
    if text:
        return text, "Фото: АдыГид"
    return place_name, "Фото: АдыГид"


def _usable(caption: str) -> bool:
    low = caption.lower()
    return not any(bad in low for bad in (
        "не обязательно", "не сама", "путают", "водяной знак", "непропаду",
    ))


def load_places() -> dict[int, dict]:
    rows = json.loads(PLACES.read_text(encoding="utf-8"))
    return {int(row["id"]): row for row in rows}


def load_before() -> list[dict]:
    return json.loads(BEFORE.read_text(encoding="utf-8"))


def _marker(kind: str, item_id: int, index: int) -> str:
    return f"<!-- adygid-carousel:{kind}:{item_id}:{index} -->"


def _figure(url: str, caption: str, credit: str) -> str:
    cap = escape(caption, quote=True)
    src = escape(url, quote=True)
    cred = escape(credit, quote=True)
    return (
        f'<figure class="shot"><img src="{src}" alt="{cap}" loading="lazy">'
        f"<figcaption>{cap}<br><small>{cred}</small></figcaption></figure>"
    )


def _photos_for(place_ids: list[int], places: dict[int, dict], used: set[str]) -> list[dict]:
    """По одному кадру с места. Если мест меньше трёх — второй кадр того же места."""
    chosen: list[dict] = []
    pools: list[tuple[dict, list[dict]]] = []
    for pid in place_ids:
        if pid in SKIP_PLACE_IDS:
            continue
        place = places.get(pid)
        if not place:
            raise KeyError(f"нет места {pid} в снимке фото")
        pool = []
        for photo in place.get("photos") or []:
            url = photo.get("url") or ""
            upload = _UPLOAD_RE.search(url)
            key = upload.group(1) if upload else url
            if not url or key in used:
                continue
            caption, credit = _split_caption(photo.get("caption") or "", place["name"])
            if not _usable(caption) or not _usable(credit):
                continue
            pool.append({"url": url, "key": key, "caption": caption, "credit": credit, "place": place["name"]})
        if pool:
            pools.append((place, pool))
    for _place, pool in pools:
        photo = pool.pop(0)
        chosen.append(photo)
        used.add(photo["key"])
    if len(chosen) < 3:
        for _place, pool in pools:
            while pool and len(chosen) < 3:
                photo = pool.pop(0)
                if photo["key"] in used:
                    continue
                chosen.append(photo)
                used.add(photo["key"])
    if len(chosen) > 5:
        chosen = chosen[:5]
    return chosen


def _insert(html: str, heading: str | None, block: str) -> str:
    if heading is None:
        match = _HEADING_RE.search(html)
        if not match:
            raise ValueError("в тексте нет заголовка, некуда поставить ленту в начало")
        return html[: match.start()] + block + "\n" + html[match.start() :]
    found = False

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        title = _plain(match.group(2))
        if found or title != heading:
            return match.group(0)
        found = True
        return match.group(0) + "\n" + block + "\n"

    updated = _HEADING_RE.sub(repl, html)
    if not found:
        raise ValueError(f"нет заголовка {heading!r}")
    return updated


def apply_html(html: str, kind: str, item_id: int, carousels: list, places: dict[int, dict]) -> tuple[str, list[dict]]:
    used = set(_UPLOAD_RE.findall(html or ""))
    report = []
    updated = html or ""
    for index, (heading, place_ids) in enumerate(carousels, start=1):
        marker = _marker(kind, item_id, index)
        if marker in updated:
            report.append({"index": index, "heading": heading, "skipped": "already"})
            continue
        photos = _photos_for(list(place_ids), places, used)
        if len(photos) < 3:
            raise ValueError(
                f"{kind} {item_id} лента {index}: набралось {len(photos)} кадров, нужно от 3"
            )
        block = marker + "\n" + "\n".join(
            _figure(photo["url"], photo["caption"], photo["credit"]) for photo in photos
        )
        updated = _insert(updated, heading, block)
        report.append({
            "index": index,
            "heading": heading,
            "count": len(photos),
            "photos": [
                {"place": photo["place"], "caption": photo["caption"], "credit": photo["credit"], "url": photo["url"]}
                for photo in photos
            ],
        })
    return updated, report


def apply_all(rows: list[dict], places: dict[int, dict]) -> tuple[list[dict], list[dict]]:
    """Вернуть (изменённые строки с new_body, отчёт)."""
    by_key = {(row["kind"], row["id"]): row for row in rows}
    changed = []
    report = []
    for kind, item_id, carousels in PLAN:
        row = by_key.get((kind, item_id))
        if row is None:
            raise KeyError(f"в снимке нет {kind} {item_id}")
        new_body, details = apply_html(row["body"], kind, item_id, carousels, places)
        changed.append({**row, "new_body": new_body})
        report.append({
            "kind": kind,
            "id": item_id,
            "slug": row.get("slug"),
            "title": row.get("title"),
            "carousels": details,
        })
    return changed, report


_DOLLAR = "$carousel$"


def _sql_literal(html: str) -> str:
    if _DOLLAR in html:
        raise ValueError("в тексте встретилась метка доллара, которой квотируется SQL")
    return _DOLLAR + html + _DOLLAR


def sql_forward(changed: list[dict]) -> str:
    table = {"article": "articles", "trail": "trails", "scenario": "scenarios"}
    column = {"article": "body", "trail": "description", "scenario": "lead"}
    lines = [
        "-- Ленты фото в статьях, маршрутах и сценариях.",
        "-- Строка меняется только если текст совпадает со снимком before.json.",
        "-- Карточки мест не затрагиваются. Повторный запуск ничего не пишет:",
        "-- после первой правки хеш уже другой.",
        "BEGIN;",
    ]
    for row in changed:
        tbl = table[row["kind"]]
        col = column[row["kind"]]
        lines.append(
            "UPDATE {tbl} SET {col} = {lit}\n"
            "WHERE id = {id} AND md5(convert_to(coalesce({col}, ''), 'UTF8')) = '{md5}';".format(
                tbl=tbl, col=col, lit=_sql_literal(row["new_body"]), id=row["id"], md5=row["md5"],
            )
        )
    lines.append(
        "DO $check$\n"
        "DECLARE missing int;\n"
        "BEGIN\n"
        "  -- Если какая-то строка уже не совпала со снимком, UPDATE выше её не тронул.\n"
        "  -- Здесь мы не можем отличить «уже применено» от «текст уехал»:\n"
        "  -- для уже применённых строк метка ленты есть, для чужих правок её нет.\n"
        "  SELECT count(*) INTO missing FROM (\n"
        + "    UNION ALL\n".join(
            "    SELECT 1 FROM {tbl} WHERE id = {id} AND position('adygid-carousel:{kind}:{id}:' in coalesce({col}, '')) = 0".format(
                tbl=table[row["kind"]], col=column[row["kind"]], id=row["id"], kind=row["kind"],
            )
            for row in changed
        )
        + "\n  ) q;\n"
        "  IF missing <> 0 THEN\n"
        "    RAISE EXCEPTION 'ленты не встали: % строк без метки. Откатите транзакцию, текст на сайте уже другой.', missing;\n"
        "  END IF;\n"
        "END\n"
        "$check$;\n"
        "COMMIT;\n"
    )
    return "\n".join(lines)


def sql_rollback(changed: list[dict]) -> str:
    table = {"article": "articles", "trail": "trails", "scenario": "scenarios"}
    column = {"article": "body", "trail": "description", "scenario": "lead"}
    lines = [
        "-- Вернуть тексты к снимку до лент. Срабатывает только если в тексте",
        "-- ещё стоит метка этой правки, чтобы не затереть более новый текст.",
        "BEGIN;",
    ]
    for row in changed:
        tbl = table[row["kind"]]
        col = column[row["kind"]]
        lines.append(
            "UPDATE {tbl} SET {col} = {lit}\n"
            "WHERE id = {id} AND position('adygid-carousel:{kind}:{id}:' in coalesce({col}, '')) > 0;".format(
                tbl=tbl, col=col, lit=_sql_literal(row["body"]), id=row["id"], kind=row["kind"],
            )
        )
    lines.append("COMMIT;\n")
    return "\n".join(lines)
