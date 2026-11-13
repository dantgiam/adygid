// Перенос test-core-v2.cjs. Запуск: node --test tests/podbor/test-core-v2.cjs
// Сверка длительностей с сырым снимком API не входит: снимка в репозитории нет,
// а в разметке источник visit.source уже записан.
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const C = require(path.join(__dirname, "../../site_app/static/podbor-core.js"));
const D = require(path.join(__dirname, "../fixtures/podbor-markup.json")).items;
const K = (x) => x.type + ":" + x.id;
const combos = [];
for (const season of ["winter", "summer", "any"])
for (const duration of ["one", "short", "long"])
for (const base of ["maykop", "khadzhokh", "dakhovskaya", "guzeripl", "lago", "any"])
for (const party of ["solo", "couple", "family", "small", "any"])
for (const been of ["first", "some", "often", "any"])
for (const pace of ["calm", "balanced", "active", "any"])
for (const interests of [[], ["views"], ["water"], ["caves"], ["culture"], ["thermal"], ["familyfun"], ["water", "caves"], ["culture", "thermal"]])
  combos.push({ season, duration, base, party, been, pace, interests });

test("snapshot: 25 routes + 66 places, every item has tags, tier, coords, visit", () => {
  assert.equal(D.filter((x) => x.type === "route").length, 25);
  assert.equal(D.filter((x) => x.type === "place").length, 66);
  for (const x of D) {
    assert.ok(x.tags.length, x.name);
    assert.ok(x.visit.typ > 0);
    assert.ok(x.lat && x.lon, x.name);
    assert.ok(["card", "estimate"].includes(x.visit.source));
  }
});

test("card durations are labelled as card, estimates as estimate", () => {
  for (const x of D) {
    if (x.visit.source === "card") assert.match(x.visit.note, /карточки|маршрута/);
    else {
      assert.equal(x.visit.source, "estimate");
      assert.match(x.visit.note, /оценка/);
    }
  }
});

test(`interest dominance + also ≤25% across ${combos.length} answer combos`, () => {
  for (const a of combos) {
    const R = C.rankAll(D, a, { phase: combos.indexOf(a) % 5 });
    if (a.interests.length) {
      assert.ok(R.main.every((z) => z.s.match > 0));
      assert.ok(R.also.every((z) => z.s.match === 0));
      const minMain = Math.min(...R.main.map((z) => z.s.total));
      assert.ok(R.also.every((z) => z.s.total < minMain), "non-matching outranks matching");
      const tot = R.main.length + R.also.length;
      if (tot) assert.ok(R.also.length / tot <= 0.25 + 1e-9);
    } else {
      assert.equal(R.also.length, 0);
      assert.equal(R.mode, "all");
    }
    for (const z of [...R.main, ...R.also]) assert.equal(C.exclusionReasons(z.x, a).length, 0);
  }
});

test("winter excludes summer-only and hard/extreme unknown; small kids only easy+kid", () => {
  const R = C.rankAll(D, { season: "winter", party: "small" }, {});
  for (const z of R.main) {
    assert.notEqual(z.x.winter_ok, "no");
    assert.equal(z.x.difficulty, "easy");
    assert.ok(z.x.kid);
  }
  assert.ok(!R.main.some((z) => K(z.x) === "place:84"));
  assert.ok(!R.main.some((z) => K(z.x) === "place:54"));
});

test("few-matches and none modes are honest", () => {
  let R = C.rankAll(D, { party: "small", interests: ["thermal"], season: "winter" }, {});
  assert.ok(["few", "ok"].includes(R.mode));
  R = C.rankAll(D, { season: "winter", pace: "calm", interests: ["caves"], party: "small" }, {});
  assert.ok(["none", "few"].includes(R.mode));
  if (R.mode === "none") {
    assert.equal(R.main.length, 0);
    assert.equal(R.also.length, 0);
  }
});

test("experience: first → best on top; often → unusual dominates but ≥1 best kept", () => {
  const f = C.rankAll(D, { been: "first" }, {});
  const o = C.rankAll(D, { been: "often" }, {});
  const top = (R, n) => R.main.slice(0, n).map((z) => z.x.editorial);
  assert.ok(top(f, 6).filter((e) => e === "best").length >= 3, "first: best in top6");
  assert.ok(top(o, 10).filter((e) => e === "unusual").length >= 5, "often: unusual in top10");
  assert.ok(top(o, 10).includes("best"), "often keeps one best");
  const s = C.rankAll(D, { been: "some", interests: ["water"] }, {});
  assert.ok(s.main.every((z) => z.s.match > 0));
});

test("«Уже был тут» hides an item and something else takes its place", () => {
  const a = { interests: ["water"] };
  const R1 = C.rankAll(D, a, {});
  const first = K(R1.main[0].x);
  const R2 = C.rankAll(D, a, { seen: new Set([first]) });
  assert.ok(!R2.main.some((z) => K(z.x) === first));
  assert.equal(R2.hidden.length, 1);
  assert.equal(R2.main.length, R1.main.length - 1);
});

test("day plans respect time budget with buffer, cap, no duplicates, routes absorb their stops", () => {
  let maxPts = 0;
  let days3plus = 0;
  for (const a of combos.filter((_, i) => i % 7 === 0)) {
    const R = C.rankAll(D, a, {});
    const days = C.planDays(R, a, {});
    const B = C.dayBudget(a);
    const seen = new Set();
    for (const d of days) {
      if (d.empty) continue;
      assert.ok(d.stops.length <= B.cap);
      if (!d.long) assert.ok(d.totalMin <= B.limit, `over budget ${d.totalMin}>${B.limit}`);
      for (const z of d.stops) {
        const k = K(z.x);
        assert.ok(!seen.has(k), "dup " + k);
        seen.add(k);
        if (z.x.type === "route") z.x.stops.forEach((id) => seen.add("place:" + id));
      }
      maxPts = Math.max(maxPts, d.stops.length);
      if (d.stops.length >= 3) days3plus++;
      if (a.interests.length && R.main.length && d === days[0]) assert.equal(d.stops[0].kind, "main", "day 1 seeded by interest item");
    }
  }
  assert.ok(maxPts >= 4, "some days reach 4+ points");
  assert.ok(days3plus > 50, "3+ points/day common: " + days3plus);
});

test("short points → 4–5 per day possible (active, Даховская, summer)", () => {
  const a = { season: "summer", duration: "one", base: "dakhovskaya", pace: "active" };
  const d = C.planDays(C.rankAll(D, a, {}), a, {})[0];
  assert.ok(d.stops.length >= 4, "got " + d.stops.length);
});

test("Maykop culture: route «Майкоп пешком» absorbs its museums (no duplicates)", () => {
  const a = { season: "summer", duration: "one", base: "maykop", pace: "active", interests: ["culture"] };
  const d = C.planDays(C.rankAll(D, a, {}), a, {})[0];
  const r = d.stops.find((z) => z.x.type === "route");
  if (r) for (const z of d.stops) if (z.x.type === "place") assert.ok(!r.x.stops.includes(z.x.id));
});

test("drive estimate: same point 0, Maykop→Даховская ≈ 50–90 min, monotonic", () => {
  assert.equal(C.driveMin([44.6, 40.1], [44.6, 40.1]), 0);
  const m = C.driveMin(C.baseAnchor("maykop"), C.baseAnchor("dakhovskaya"));
  assert.ok(m >= 50 && m <= 90, m);
  assert.ok(C.driveMin(C.baseAnchor("maykop"), C.baseAnchor("lago")) > m);
});

test("budgets: winter shorter than summer for active; small kids −20%", () => {
  assert.ok(C.dayBudget({ pace: "active", season: "winter" }).budget < C.dayBudget({ pace: "active", season: "summer" }).budget);
  assert.equal(C.dayBudget({ pace: "balanced", party: "small" }).budget, Math.round(450 * 0.8));
});

test("reshuffle: phase rotates order inside equal groups but keeps the set", () => {
  const a = { season: "winter" };
  const r0 = C.rankAll(D, a, { phase: 0 }).main.map((z) => K(z.x));
  const r1 = C.rankAll(D, a, { phase: 1 }).main.map((z) => K(z.x));
  assert.deepEqual([...r0].sort(), [...r1].sort());
  assert.notDeepEqual(r0, r1);
});

test("event has no PII fields", () => {
  const e = C.makeEvent("s1", "answer", { question_id: "party", answer_code: "family" });
  assert.deepEqual(
    Object.keys(e).sort(),
    ["algorithm_version", "anonymous_session_id", "answer_code", "event_id", "event_type", "item_key", "plan_id", "question_id", "skipped", "ts"].sort(),
  );
});
