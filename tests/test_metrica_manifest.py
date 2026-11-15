"""Манифест целей Метрики совпадает с тем, что реально шлёт публичный сайт."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_FILES = [
    ROOT / "site_app" / "static" / "site.js",
    ROOT / "site_app" / "static" / "podbor.js",
    ROOT / "site_app" / "static" / "partners.js",
]
GOAL_CALL = re.compile(r"""(?:adygidGoal|goal)\(\s*["']([a-z][a-z0-9_]*)["']""")
NAMED = re.compile(
    r"""["'](podbor_q[1-7]_done|plan_save_(?:max|tg)|magnet_click_(?:max|tg)|read_(?:25|50|75|100))["']"""
)


def _manifest():
    return json.loads((ROOT / "site_app" / "data" / "metrica_goals.json").read_text(encoding="utf-8"))


def test_manifest_is_unique_and_within_the_counter_limit():
    doc = _manifest()
    ids = [event["id"] for event in doc["events"]]
    assert doc["counter_id"] == "111028002"
    assert doc["account_goals_before"] == 82
    assert doc["goal_limit"] == 200
    assert doc["slots_remaining_before"] == 118
    assert len(ids) == len(set(ids))
    assert "bot_max_click" not in ids
    assert doc["new_goals_to_create"] == sum(1 for event in doc["events"] if event["account_status"] == "new")
    assert doc["new_goals_to_create"] <= 118
    assert doc["emitted_total"] == len(ids)
    assert all(event["emitted"] is True for event in doc["events"])
    missing = {
        "podbor_edit_click", "podbor_save_click", "club_click", "phone_click", "email_click",
        "bot_click_max", "bot_click_tg", "article_internal_link", "outbound_click", "review_click",
        "podbor_share_click", "podbor_shared_open", "podbor_yamaps_click", "podbor_club_click",
        "seasonal_click", "plan_save_max", "plan_save_tg", "partner_form_submit", "partner_cta_click",
    }
    for event in doc["events"]:
        if event["id"] in missing:
            assert event["account_status"] == "new" and event["in_code_before"] is True
    assert doc["preserved_not_emitted"][0]["id"] == "bot_max_click"
    assert doc["preserved_not_emitted"][0]["emitted"] is False
    core = (ROOT / "site_app" / "static" / "metrica-core.js").read_text(encoding="utf-8")
    for event_id in ids:
        assert f'"{event_id}"' in core


def test_every_emitted_goal_name_is_in_the_manifest_and_bot_max_click_is_not_sent():
    doc = _manifest()
    known = {event["id"] for event in doc["events"]}
    found = set()
    for path in JS_FILES:
        text = path.read_text(encoding="utf-8")
        found.update(GOAL_CALL.findall(text))
        found.update(NAMED.findall(text))
        assert "bot_max_click" not in text
    found.discard("read_")
    found.update({"read_25", "read_50", "read_75", "read_100"})
    assert found <= known
    added = [event["id"] for event in doc["events"] if event["account_status"] == "new"]
    blobs = "\n".join(path.read_text(encoding="utf-8") for path in JS_FILES)
    for event_id in added:
        assert event_id in blobs


def test_public_template_loads_sanitizer_before_site_js_and_does_not_change_consent_copy():
    base = (ROOT / "site_app" / "templates" / "base.html").read_text(encoding="utf-8")
    core_at = base.rfind('src="/assets/metrica-core.js')
    site_at = base.rfind('src="/assets/site.js')
    assert 0 <= core_at < site_at
    assert ">Принять</button>" in base
    assert ">Только необходимые</button>" in base
    js = (ROOT / "site_app" / "static" / "site.js").read_text(encoding="utf-8")
    assert "if (!window.ADYGID_METRIKA_ID) return;" in js
    assert 'consent === "necessary"' in js
    assert "queue.length = 0" in js
    assert "page_title" not in js
    assert "plan_id" not in js
    podbor = (ROOT / "site_app" / "static" / "podbor.js").read_text(encoding="utf-8")
    assert "goal(goalName, params)" in podbor
    assert "plan_id: ready.id }, params" not in podbor
    assert 'goal("podbor_feedback_max", {})' in podbor
