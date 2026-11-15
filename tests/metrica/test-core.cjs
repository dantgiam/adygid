const test = require("node:test");
const assert = require("node:assert");
const M = require("../../site_app/static/metrica-core.js");
const manifest = require("../../site_app/data/metrica_goals.json");

test("manifest ids match the sanitizer and stay inside the free slots", () => {
  const ids = manifest.events.map((e) => e.id);
  assert.deepEqual(ids, M.EXISTING.concat(M.MISSING_IN_ACCOUNT, M.ADDED));
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(manifest.counter_id, "111028002");
  assert.equal(manifest.account_goals_before, 82);
  assert.equal(manifest.goal_limit, 200);
  assert.ok(manifest.new_goals_to_create <= 118);
  assert.equal(manifest.new_goals_to_create, manifest.events.filter((e) => e.account_status === "new").length);
  assert.ok(!ids.includes("bot_max_click"));
  assert.equal(manifest.preserved_not_emitted[0].id, "bot_max_click");
  assert.equal(manifest.preserved_not_emitted[0].emitted, false);
  for (const id of M.MISSING_IN_ACCOUNT) {
    const row = manifest.events.find((e) => e.id === id);
    assert.equal(row.account_status, "new");
    assert.equal(row.in_code_before, true);
    assert.equal(row.emitted, true);
  }
  for (const id of M.ADDED) {
    const row = manifest.events.find((e) => e.id === id);
    assert.equal(row.account_status, "new");
    assert.equal(row.in_code_before, false);
  }
});

test("sanitize keeps stable ids and drops PII, urls, queries and plan tokens", () => {
  const review = M.sanitize("review_click", {
    page_type: "place",
    page_id: "50",
    messenger: "max",
    page_title: "Хаджох и Иван +7 900 000-00-00",
    plan_id: "abcdefgh",
    email: "a@b.c",
    query: "куда поехать",
  });
  assert.deepEqual(review.params, { page_type: "place", page_id: "50", messenger: "max" });

  const link = M.sanitize("article_internal_link", {
    href: "/stati/rufabgo?q=секрет#map",
    page: "https://adygid.ru/mesta/50?utm=1",
  });
  assert.equal(link.params.href, "/stati/{slug}");
  assert.equal(link.params.slug, "rufabgo");
  assert.equal(link.params.page, "/mesta/{id}");
  assert.equal(link.params.item, "place:50");
  assert.ok(!JSON.stringify(link.params).includes("секрет"));
  assert.ok(!JSON.stringify(link.params).includes("utm"));

  const save = M.sanitize("plan_save_max", { days: 3, plan_id: "k7Qm9xYz", hash: "plan=winter.one" });
  assert.deepEqual(save.params, { days: 3 });

  assert.equal(M.sanitize("bot_max_click", { placement: "nav" }), null);
  assert.equal(M.sanitize("not_a_goal", {}), null);

  const phone = M.sanitize("phone_click", { placement: "page", href: "tel:+79000000000" });
  assert.deepEqual(phone.params, { placement: "page" });
});

test("filter values and podbor answers stay on the allowlist", () => {
  assert.deepEqual(M.sanitize("filter_apply", {
    page: "/mesta?type=3",
    field: "district",
    value: "khadzhokh",
  }).params, { page: "/mesta", field: "district", value: "khadzhokh" });
  assert.equal(M.sanitize("filter_apply", { page: "/mesta", field: "type", value: "Водопады" }).params.value, undefined);
  assert.deepEqual(M.sanitize("podbor_q7_done", { q: "interests", interests: "water,caves", skipped: 0 }).params.interests, "water,caves");
  assert.equal(M.sanitize("podbor_q7_done", { q: "interests", interests: "секретный текст", skipped: 0 }).params.interests, undefined);
  assert.equal(M.sanitize("podbor_answer", { q: "childage", answer: "tiny", skipped: 1 }).params.answer, "tiny");
  assert.equal(M.sanitize("podbor_answer", { q: "season", answer: "tiny", skipped: 0 }).params.q, "season");
});

test("admin, auth and localhost are not tracked", () => {
  assert.equal(M.blocked({ hostname: "adygid.ru", pathname: "/mesta/50" }), false);
  assert.equal(M.blocked({ hostname: "adygid.ru", pathname: "/partners" }), false);
  assert.equal(M.blocked({ hostname: "adygid.ru", pathname: "/admin/partners" }), true);
  assert.equal(M.blocked({ hostname: "adygid.ru", pathname: "/api/partners/apply" }), true);
  assert.equal(M.blocked({ hostname: "adygid.ru", pathname: "/login" }), true);
  assert.equal(M.blocked({ hostname: "localhost", pathname: "/" }), true);
  assert.equal(M.blocked({ hostname: "127.0.0.1", pathname: "/podbor" }), true);
});
