"""Собрать идемпотентную миграцию трёх зимних статей и откат к снимку «до».

Не ходит в базу. Пишет:
  migrations/20261115_winter_intent_articles.sql
  migrations/20261115_winter_intent_articles_rollback.sql
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_FORWARD = ROOT / "migrations" / "20261115_winter_intent_articles.sql"
SQL_ROLLBACK = ROOT / "migrations" / "20261115_winter_intent_articles_rollback.sql"

_spec = importlib.util.spec_from_file_location(
    "winter_articles", ROOT / "content" / "winter-intent-2026-11" / "articles.py"
)
articles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(articles)


def _dollar(tag: str, text: str) -> str:
    fence = f"${tag}$"
    if fence in text:
        raise SystemExit(f"{tag} встречается в тексте")
    return fence + text + fence


def _faq(items) -> str:
    return _dollar("faq", json.dumps(items or [], ensure_ascii=False, separators=(",", ":")))


def _array(ids) -> str:
    return "ARRAY[" + ",".join(str(int(i)) for i in ids) + "]::integer[]"


def _article_sql(article: dict, *, forward: bool) -> str:
    before = article["before"]
    old = {
        "title": before["title"],
        "excerpt": before["excerpt"] or "",
        "body": before["body"],
        "faq": before["faq"] or [],
        "featured": list(before["featured_checkpoint_ids"] or []),
    }
    new = {
        "title": article["title"],
        "excerpt": article["excerpt"],
        "body": article["body"],
        "faq": article["faq"],
        "featured": list(article["featured_checkpoint_ids"]),
    }
    src, dst = (old, new) if forward else (new, old)
    tag = f"a{article['id']}{'f' if forward else 'b'}"
    phrase = dst["body"][dst["body"].find("<h2>") : dst["body"].find("</h2>")]
    phrase = phrase.replace("<h2>", "").strip()
    return f"""
  -- article {article['id']} {article['slug']}
  SELECT title, excerpt, body, faq, featured_checkpoint_ids, cover_url, slug, is_published
    INTO v_title, v_excerpt, v_body, v_faq, v_feat, v_cover, v_slug, v_pub
  FROM articles WHERE id = {article['id']} FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'article {article['id']} ({article['slug']}) не найден';
  END IF;
  IF v_slug IS DISTINCT FROM '{article['slug']}' OR v_pub IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'article {article['id']}: slug или is_published не те, что в снимке';
  END IF;
  IF v_title = {_dollar(tag + 't2', dst['title'])}
     AND v_excerpt IS NOT DISTINCT FROM {_dollar(tag + 'e2', dst['excerpt'])}
     AND v_body = {_dollar(tag + 'b2', dst['body'])}
     AND v_faq = {_faq(dst['faq'])}::jsonb
     AND v_feat = {_array(dst['featured'])} THEN
    NULL; -- уже в целевом состоянии
  ELSIF v_title = {_dollar(tag + 't1', src['title'])}
     AND v_excerpt IS NOT DISTINCT FROM {_dollar(tag + 'e1', src['excerpt'])}
     AND v_body = {_dollar(tag + 'b1', src['body'])}
     AND v_faq = {_faq(src['faq'])}::jsonb
     AND v_feat = {_array(src['featured'])} THEN
    UPDATE articles
       SET title = {_dollar(tag + 't3', dst['title'])},
           excerpt = {_dollar(tag + 'e3', dst['excerpt'])},
           body = {_dollar(tag + 'b3', dst['body'])},
           faq = {_faq(dst['faq'])}::jsonb,
           featured_checkpoint_ids = {_array(dst['featured'])},
           updated_at = now()
     WHERE id = {article['id']}
       AND slug = '{article['slug']}'
       AND is_published IS TRUE;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> 1 THEN
      RAISE EXCEPTION 'article {article['id']}: обновлена не одна строка (%)', v_n;
    END IF;
  ELSE
    RAISE EXCEPTION 'article {article['id']} ({article['slug']}) не совпал ни со снимком «до», ни с целевым текстом — строку не трогаем';
  END IF;
  IF (SELECT cover_url FROM articles WHERE id = {article['id']}) IS DISTINCT FROM v_cover
     OR (SELECT slug FROM articles WHERE id = {article['id']}) IS DISTINCT FROM '{article['slug']}'
     OR (SELECT is_published FROM articles WHERE id = {article['id']}) IS DISTINCT FROM TRUE
     OR (SELECT featured_trail_ids FROM articles WHERE id = {article['id']}) IS DISTINCT FROM v_trails
     OR (SELECT position('{phrase.replace("'", "''")}' IN body) FROM articles WHERE id = {article['id']}) = 0 THEN
    RAISE EXCEPTION 'article {article['id']}: после шага съехали обложка, адрес, публикация или текст';
  END IF;
""".replace("v_trails", "v_trails")


def render(forward: bool) -> str:
    steps = "\n".join(_article_sql(a, forward=forward) for a in articles.ARTICLES)
    # featured_trail_ids снимок до шага: читаем вместе с остальными полями.
    steps = steps.replace(
        "SELECT title, excerpt, body, faq, featured_checkpoint_ids, cover_url, slug, is_published\n"
        "    INTO v_title, v_excerpt, v_body, v_faq, v_feat, v_cover, v_slug, v_pub",
        "SELECT title, excerpt, body, faq, featured_checkpoint_ids, cover_url, slug, is_published, featured_trail_ids\n"
        "    INTO v_title, v_excerpt, v_body, v_faq, v_feat, v_cover, v_slug, v_pub, v_trails",
    )
    kind = "применение" if forward else "откат"
    expect = "целевой" if forward else "исходный"
    return f"""-- Зимние вопросы: три существующие статьи. {kind}.
-- Идентификаторы живой базы на 15.11.2026:
--   33 adygeya-v-dekabre
--   14 lago-naki-zimoy-na-mashine
--   15 pervyy-sneg-na-lago-naki-ehat-ili-net
-- Повторный запуск ничего не меняет. Если текст статьи уже не совпадает
-- ни со снимком, ни с {expect} версией, скрипт падает и не перезаписывает строку.
-- Не меняет slug, cover_url, district, is_published, featured_trail_ids.
-- Не трогает другие статьи, маршруты и места. Маршрут 11 и место 50
-- сверяются по хешу до и после. Не запускать scripts/seo_content_publish.py --live:
-- тот скрипт переписывает весь ноябрьский пакет, а не эти три строки.
-- Базу из облака не трогали: скрипт только для исполнителя на своей стороне.

BEGIN;

CREATE TEMP TABLE winter_intent_guard_articles AS
SELECT id, md5(convert_to(coalesce(body, ''), 'UTF8')) AS body_md5
FROM articles
WHERE id NOT IN (14, 15, 33);

CREATE TEMP TABLE winter_intent_guard_frozen AS
SELECT 'trail-11'::text AS k,
       md5(convert_to(coalesce(name, '') || '|' || coalesce(description, ''), 'UTF8')) AS h
FROM trails WHERE id = 11
UNION ALL
SELECT 'place-50'::text,
       md5(convert_to(coalesce(name, '') || '|' || coalesce(description, ''), 'UTF8'))
FROM checkpoints WHERE id = 50;

DO $migrate$
DECLARE
  v_title text;
  v_excerpt text;
  v_body text;
  v_faq jsonb;
  v_feat integer[];
  v_cover text;
  v_slug text;
  v_pub boolean;
  v_trails integer[];
  v_n int;
  v_articles int;
BEGIN
  SELECT count(*) INTO v_articles FROM articles;
  IF (SELECT count(*) FROM winter_intent_guard_frozen) <> 2 THEN
    RAISE EXCEPTION 'precheck: нет маршрута 11 или места 50';
  END IF;
  IF (SELECT count(*) FROM articles WHERE id IN (14, 15, 33)) <> 3 THEN
    RAISE EXCEPTION 'precheck: среди статей 14, 15 и 33 кого-то нет';
  END IF;
{steps}
  IF (SELECT count(*) FROM articles) <> v_articles THEN
    RAISE EXCEPTION 'postcheck: число статей изменилось';
  END IF;
  IF EXISTS (
    SELECT 1 FROM winter_intent_guard_frozen g
    JOIN (
      SELECT 'trail-11'::text AS k,
             md5(convert_to(coalesce(name, '') || '|' || coalesce(description, ''), 'UTF8')) AS h
      FROM trails WHERE id = 11
      UNION ALL
      SELECT 'place-50'::text,
             md5(convert_to(coalesce(name, '') || '|' || coalesce(description, ''), 'UTF8'))
      FROM checkpoints WHERE id = 50
    ) n USING (k)
    WHERE n.h IS DISTINCT FROM g.h
  ) THEN
    RAISE EXCEPTION 'postcheck: изменились маршрут 11 или место 50';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM winter_intent_guard_articles g
    JOIN articles a ON a.id = g.id
    WHERE md5(convert_to(coalesce(a.body, ''), 'UTF8')) IS DISTINCT FROM g.body_md5
  ) THEN
    RAISE EXCEPTION 'postcheck: изменилось тело посторонней статьи';
  END IF;
END
$migrate$;

COMMIT;
"""


def main() -> None:
    SQL_FORWARD.write_text(render(True), encoding="utf-8")
    SQL_ROLLBACK.write_text(render(False), encoding="utf-8")
    print(SQL_FORWARD, SQL_FORWARD.stat().st_size)
    print(SQL_ROLLBACK, SQL_ROLLBACK.stat().st_size)


if __name__ == "__main__":
    main()
