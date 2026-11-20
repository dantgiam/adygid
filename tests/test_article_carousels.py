"""Ленты в текстах: только вставка, идемпотентность, 3–5 кадров, откат по хешу."""
import re

from content.carousels_2026_11.apply import (
    apply_all, apply_html, body_md5, load_before, load_places, sql_forward, sql_rollback,
)
from content.carousels_2026_11.plan import PLAN
from site_app.galleries import render_article_gallery


def test_every_planned_carousel_is_three_to_five_real_photos():
    changed, report = apply_all(load_before(), load_places())
    assert len(changed) == len(PLAN)
    assert {row["kind"] for row in changed} <= {"article", "trail", "scenario"}
    for item in report:
        assert 1 <= len(item["carousels"]) <= 3
        for block in item["carousels"]:
            assert 3 <= block["count"] <= 5
            for photo in block["photos"]:
                assert photo["url"].startswith("https://")
                assert photo["caption"]
                assert photo["credit"].startswith("Фото:")
                assert "не обязательно" not in photo["caption"].lower()


def test_insert_is_idempotent_and_keeps_the_old_words():
    places = load_places()
    for row in load_before():
        spec = next(item for item in PLAN if item[0] == row["kind"] and item[1] == row["id"])
        once, _details = apply_html(row["body"], row["kind"], row["id"], spec[2], places)
        twice, second = apply_html(once, row["kind"], row["id"], spec[2], places)
        assert twice == once
        assert all(block.get("skipped") == "already" for block in second)
        assert body_md5(row["body"]) == row["md5"]
        # Старые слова на месте: мы только дописываем фигуры.
        old_words = set(re.sub(r"<[^>]+>", " ", row["body"]).split())
        new_words = set(re.sub(r"<[^>]+>", " ", once).split())
        assert old_words <= new_words


def test_renderer_groups_each_insertion_into_one_gallery():
    changed, report = apply_all(load_before(), load_places())
    by_id = {(row["kind"], row["id"]): row for row in changed}
    for item in report:
        row = by_id[(item["kind"], item["id"])]
        html = render_article_gallery(row["new_body"])
        galleries = re.findall(r'class="article-gallery"', html)
        assert len(galleries) == len(item["carousels"]), (item["kind"], item["id"], len(galleries))
        assert f"adygid-carousel:{item['kind']}:{item['id']}:" in row["new_body"]


def test_sql_updates_only_matching_hash_and_rolls_back():
    changed, _report = apply_all(load_before(), load_places())
    forward = sql_forward(changed)
    backward = sql_rollback(changed)
    assert "checkpoints" not in forward.lower()
    assert "md5(convert_to" in forward
    for row in changed:
        assert row["md5"] in forward
        assert f"adygid-carousel:{row['kind']}:{row['id']}:" in backward
    # Повтор: хеш уже другой, UPDATE не совпадёт, но метка есть и проверка проходит.
    assert "RAISE EXCEPTION" in forward
