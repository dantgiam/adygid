// Браузерный прогон публичных действий: одно событие, чистый payload, ym может отсутствовать.
// Запуск: node --test tests/metrica/browser.cjs
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const ROOT = path.resolve(__dirname, "../..");

function page(origin) {
  const src = (name) => origin + "/assets/" + name;
  const boot = {
    items: [{
      type: "place", id: 1, name: "Тестовое место", url: "/mesta/1", tags: ["views"],
      visit: { min: 60, typ: 90, max: 120, source: "estimate" },
      difficulty: "easy", kid: true, winter_ok: "yes", lat: 44.2, lon: 40.2,
      area: "khadzhokh", stops: [], editorial: "best", indoor: false, image: "", stroller: "no"
    }],
    copy: {}, refine: [], src: "direct", season: "", fresh: false
  };
  return `<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"></head><body>
<header class="site-header"><a class="brand" href="/">АдыГид</a>
<nav class="main-nav"><a id="nav-places" href="/mesta">Места</a><a class="header-cta" href="/klub">Клуб</a></nav>
<button type="button" id="menu-toggle">меню</button>
<nav id="mobile-menu" hidden><a id="menu-articles" href="/stati">Статьи</a></nav></header>
<a class="card article-card" id="article-card" href="/stati/rufabgo">Статья</a>
<a class="card" id="place-card" href="/mesta/50">Место</a>
<a class="door" id="door" href="/kuda/s-detmi">С детьми</a>
<form class="filters" id="filters"><select name="type" id="filter-type"><option value="">Любой</option><option value="3">Водопады SECRETNAME</option></select>
<a class="reset" id="filter-reset" href="/mesta">Сбросить</a></form>
<button type="button" class="fav-btn" data-type="place" data-id="50"><span class="fav-btn-text">В избранное</span></button>
<button type="button" class="diff-info-btn" id="diff">?</button><div class="diff-popover"></div>
<div data-pcar><div data-pcar-track><div data-pcar-slide><img alt=""></div><div data-pcar-slide><img alt=""></div></div>
<button data-pcar-next id="gal-next">next</button></div>
<section class="faq-block"><details class="faq-item" open><summary>Первый вопрос SECRETNAME</summary><div></div></details>
<details class="faq-item"><summary id="faq-2">Второй вопрос</summary><div></div></details></section>
<a class="club-cta" href="/klub"><span class="btn" id="club-btn">Открыть клуб</span></a>
<form id="partner-form" data-taxonomy='[{"code":"adventure","subs":[{"code":"rafting","title":"Сплав"}]}]'>
<input id="pf-company" name="company"><select id="pf-cat" name="category"><option value="adventure">Приключения</option></select>
<select id="pf-sub" name="subcategory"></select>
<input id="pf-loc" name="location"><textarea id="pf-services" name="services"></textarea>
<input id="pf-discount" name="discount" value="5%"><input name="consent" type="checkbox">
<p id="pf-error" hidden></p><button id="pf-submit" type="submit">Отправить</button></form>
<div id="partner-done" hidden><span id="pd-code"></span><p id="pd-text"></p>
<a id="pd-max" href="https://max.ru/se15002131_bot">MAX</a><a id="pd-tg" href="https://t.me/adygid_bot">TG</a></div>
<div id="podbor-root"><div id="wizard"></div><div id="results"></div><div id="podbor-layout"></div>
<div id="podbor-reaction"><p id="podbor-reaction-text"></p><div id="podbor-flash"></div><div id="podbor-loader"></div></div>
<div id="review-sheet"></div><div id="podbor-toast"></div>
<script id="podbor-boot" type="application/json">${JSON.stringify(boot)}</script></div>
<div id="cookie-banner" hidden><button id="cookie-accept">Принять</button><button id="cookie-necessary">Только необходимые</button></div>
<a id="cookie-settings" href="#cookie-banner">Настройки cookie</a>
<pre id="out"></pre>
<script>
try { localStorage.setItem("adygid_cookie_consent", "accepted"); } catch (e) {}
window.ADYGID_METRIKA_ID = 111028002;
window.ADYGID_METRICA_ALLOW_HOST = true;
window.__ym = [];
window.__fetches = [];
window.ym = function () { window.__ym.push(Array.from(arguments)); };
(function () {
  var proto = window.HTMLScriptElement && HTMLScriptElement.prototype;
  if (!proto) return;
  var desc = Object.getOwnPropertyDescriptor(proto, "src");
  if (!desc || !desc.set) return;
  Object.defineProperty(proto, "src", {
    configurable: true,
    get: function () { return desc.get.call(this); },
    set: function (v) { if (String(v).indexOf("mc.yandex") === -1) desc.set.call(this, v); }
  });
})();
document.addEventListener("click", function (e) {
  var a = e.target && e.target.closest && e.target.closest("a[href]");
  if (!a) return;
  var href = a.getAttribute("href") || "";
  if (href.charAt(0) === "/" || href.indexOf("http") === 0) e.preventDefault();
}, true);
HTMLFormElement.prototype.submit = function () {};
window.fetch = function (url) {
  window.__fetches.push(String(url));
  if (String(url).indexOf("/api/partners/apply") === 0) {
    var mode = window.__partnerMode || "http";
    if (mode === "ok") return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ code: "T1", contacts_via_bot: true, bot: { max: "https://max.ru/se15002131_bot", telegram: "https://t.me/adygid_bot" } }); } });
    if (mode === "network") return Promise.reject(new Error("offline"));
    return Promise.resolve({ ok: false, status: 400, json: function () { return Promise.resolve({ detail: "no" }); } });
  }
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ liked: true, count: 1, id: 1, url: "/mesta/1", name: "x" }); } });
};
var origMM = window.matchMedia ? window.matchMedia.bind(window) : null;
window.matchMedia = function (q) {
  if (String(q).indexOf("reduce") >= 0) return { matches: true, media: q, addEventListener: function(){}, removeEventListener: function(){}, addListener: function(){}, removeListener: function(){} };
  if (origMM) return origMM(q);
  return { matches: false, media: q, addEventListener: function(){}, removeEventListener: function(){}, addListener: function(){}, removeListener: function(){} };
};
</script>
<script src="${src("metrica-core.js")}"></script>
<script src="${src("site.js")}"></script>
<script src="${src("partners.js")}"></script>
<script src="${src("podbor-core.js")}"></script>
<script src="${src("podbor.js")}"></script>
<script type="module">
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (el) => el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
const goals = (name) => window.__ym.filter((c) => c[1] === "reachGoal" && c[2] === name);
const lastParams = (name) => { const row = goals(name).slice(-1)[0]; return row ? row[3] : null; };
const report = {};
function count(name) { return goals(name).length; }
try {
  report.consent = localStorage.getItem("adygid_cookie_consent");
  report.allow = window.ADYGID_METRICA_ALLOW_HOST === true;
  report.blocked = !!(window.AdygidMetrica && window.AdygidMetrica.blocked(location));
  const beforeNav = count("nav_click");
  click(document.getElementById("nav-places"));
  click(document.getElementById("nav-places"));
  report.nav_once = count("nav_click") - beforeNav;
  report.nav_params = lastParams("nav_click");

  const beforeCard = count("place_card_click");
  const navAtCard = count("nav_click");
  click(document.getElementById("place-card"));
  report.place_card = count("place_card_click") - beforeCard;
  report.place_nav = count("nav_click") - navAtCard;
  report.place_params = lastParams("place_card_click");

  click(document.getElementById("article-card"));
  report.article = goals("content_card_click").filter((c) => c[3].kind === "article").length;
  click(document.getElementById("door"));
  report.door = goals("content_card_click").filter((c) => c[3].kind === "door").length;

  document.getElementById("filter-type").value = "3";
  document.getElementById("filter-type").dispatchEvent(new Event("change", { bubbles: true }));
  report.filter = goals("filter_apply").length;
  report.filter_params = lastParams("filter_apply");
  click(document.getElementById("filter-reset"));
  report.reset = goals("filter_reset").length;

  click(document.querySelector(".fav-btn"));
  report.fav = goals("favorite_toggle").length;
  report.fav_on = document.querySelector(".fav-btn").classList.contains("active");
  report.fav_label = document.querySelector(".fav-btn-text").textContent;

  click(document.getElementById("menu-toggle"));
  report.menu_open = goals("menu_toggle").filter((c) => c[3].state === "open").length;
  click(document.getElementById("menu-articles"));
  report.menu_nav = goals("nav_click").filter((c) => c[3].area === "menu").length;

  click(document.getElementById("faq-2"));
  report.faq = goals("faq_open").length;
  report.faq_params = lastParams("faq_open");

  click(document.getElementById("diff"));
  report.diff = goals("difficulty_open").length;
  click(document.getElementById("gal-next"));
  report.gallery = goals("gallery_nav").length;

  const clubBefore = count("club_click");
  click(document.getElementById("club-btn"));
  report.club = count("club_click") - clubBefore;
  report.club_nav_extra = goals("nav_click").filter((c) => c[3].target === "/klub").length;

  window.adygidGoal("review_click", {
    page_type: "place", page_id: "50", messenger: "max",
    page_title: "SECRETNAME", plan_id: "abcdefgh", phone: "+79000000000", email: "a@b.c"
  });
  report.review = lastParams("review_click");

  const ym = window.ym;
  window.ym = undefined;
  let threw = false;
  try { window.adygidGoal("toc_click", { page: "/stati/rufabgo" }); } catch (e) { threw = true; }
  window.ym = ym;
  report.no_ym_threw = threw;
  report.toc_without_ym = goals("toc_click").length;

  const submitForm = () => document.getElementById("partner-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  const fetchesBefore = window.__fetches.length;
  submitForm();
  report.invalid = lastParams("partner_form_invalid");
  report.invalid_fetch = window.__fetches.length - fetchesBefore;

  document.getElementById("pf-company").value = "SECRETNAME клуб";
  document.getElementById("pf-cat").value = "adventure";
  document.getElementById("pf-cat").dispatchEvent(new Event("change", { bubbles: true }));
  document.getElementById("pf-sub").value = "rafting";
  document.getElementById("pf-loc").value = "Даховская";
  document.getElementById("pf-services").value = "Сплав для теста";
  document.querySelector('[name="consent"]').checked = true;
  window.__partnerMode = "http";
  submitForm();
  await sleep(30);
  report.http_error = goals("partner_form_error").filter((c) => c[3].code === "http").length;
  report.submit_before_ok = goals("partner_form_submit").length;

  window.__partnerMode = "ok";
  submitForm();
  await sleep(30);
  report.submit = goals("partner_form_submit").length;
  report.submit_params = lastParams("partner_form_submit");
  click(document.getElementById("pd-max"));
  report.bot = goals("bot_click_max").filter((c) => c[3].placement === "partners_done").length;
  report.bot_max_click = goals("bot_max_click").length;

  const season = document.querySelector('[data-act="choose"][data-answer="winter"]');
  click(season);
  report.podbor_start = goals("podbor_start").length;
  report.podbor_q1 = goals("podbor_q1_done").length;
  report.podbor_q1_params = lastParams("podbor_q1_done");
  report.podbor_buttons = document.querySelectorAll("[data-act='choose']").length;
  click(season);
  report.podbor_q1_still = goals("podbor_q1_done").length;
  await sleep(50);
  const back = document.querySelector('[data-act="back"]');
  if (back) click(back);
  report.podbor_back = goals("podbor_nav").filter((c) => c[3].action === "back").length;
  report.podbor_error = goals("podbor_error").length;

  report.goal_names = window.__ym.filter((c) => c[1] === "reachGoal").map((c) => c[2]);
  report.payload = JSON.stringify(window.__ym);
  report.ok = true;
} catch (err) {
  report.ok = false;
  report.error = String(err && err.stack || err);
}
document.getElementById("out").textContent = JSON.stringify(report);
</script>
</body></html>`;
}

function runChrome() {
  const html = page("http://127.0.0.1");
  const server = require("http").createServer((req, res) => {
    const url = (req.url || "/").split("?")[0];
    if (url === "/" || url === "/fixture") {
      res.setHeader("content-type", "text/html; charset=utf-8");
      res.end(html.replaceAll("http://127.0.0.1", "http://127.0.0.1:" + server.address().port));
      return;
    }
    if (url.startsWith("/assets/")) {
      const file = path.join(ROOT, "site_app/static", decodeURIComponent(url.slice("/assets/".length)));
      if (!file.startsWith(path.join(ROOT, "site_app/static"))) { res.statusCode = 404; res.end(); return; }
      try { res.end(fs.readFileSync(file)); } catch (e) { res.statusCode = 404; res.end(); }
      return;
    }
    res.statusCode = 404;
    res.end();
  });
  return new Promise((resolve, reject) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
    server.on("error", reject);
  }).then((live) => {
  const port = 9333 + Math.floor(Math.random() * 1000);
  const chrome = spawn("google-chrome", [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--remote-debugging-port=" + port,
    "about:blank",
  ], { stdio: "ignore" });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pageUrl = "http://127.0.0.1:" + live.address().port + "/fixture";
  async function version() {
    for (let i = 0; i < 40; i++) {
      try {
        const res = await fetch("http://127.0.0.1:" + port + "/json/version");
        if (res.ok) return res.json();
      } catch (e) { /* ещё стартует */ }
      await sleep(150);
    }
    throw new Error("devtools port did not open");
  }
  return version().then(async (ver) => {
    const ws = new WebSocket(ver.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve);
      ws.addEventListener("error", () => reject(new Error("devtools socket")));
    });
    let seq = 0;
    const waiters = new Map();
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && waiters.has(msg.id)) waiters.get(msg.id)(msg);
    });
    const send = (method, params, sessionId) => new Promise((resolve) => {
      const id = ++seq;
      waiters.set(id, resolve);
      const body = { id, method, params: params || {} };
      if (sessionId) body.sessionId = sessionId;
      ws.send(JSON.stringify(body));
    });
    const created = await send("Target.createTarget", { url: "about:blank" });
    const targetId = created.result && created.result.targetId;
    const attached = await send("Target.attachToTarget", { targetId, flatten: true });
    const sessionId = attached.result && attached.result.sessionId;
    const probe = await fetch(pageUrl);
    const probeText = await probe.text();
    if (!probe.ok || probeText.indexOf('id="out"') < 0) throw new Error("probe " + probe.status + " " + probeText.slice(0, 120));
    const nav = await send("Page.navigate", { url: pageUrl }, sessionId);
    const started = Date.now();
    let text = "";
    let last = null;
    while (Date.now() - started < 15000) {
      const ev = await send("Runtime.evaluate", {
        expression: "(function(){var o=document.getElementById('out'); if(o&&o.textContent) return o.textContent; var t=document.body?document.body.innerText.slice(0,400):'nobody'; return 'HREF '+location.href+' TEXT '+t;})()",
        returnByValue: true,
      }, sessionId);
      last = ev;
      text = ev.result && ev.result.result && ev.result.result.value || "";
      if (text && text.charAt(0) === "{") break;
      await sleep(200);
    }
    ws.close();
    chrome.kill("SIGKILL");
    live.close();
    if (!text || text.charAt(0) !== "{") throw new Error("no report " + pageUrl + " nav " + JSON.stringify(nav).slice(0, 300) + " " + JSON.stringify(last).slice(0, 500));
    return JSON.parse(text);
  }).catch((err) => {
    chrome.kill("SIGKILL");
    live.close();
    throw err;
  });
  });
}

test("browser: one event per action, sanitized payload, no ym throw, old controls still work", async () => {
  const r = await runChrome();
  assert.equal(r.ok, true, r.error);
  assert.equal(r.nav_once, 1, JSON.stringify({ consent: r.consent, allow: r.allow, blocked: r.blocked, nav: r.nav_params, names: r.goal_names }));
  assert.equal(r.nav_params.area, "header");
  assert.equal(r.nav_params.target, "/mesta");
  assert.equal(r.place_card, 1);
  assert.equal(r.place_nav, 0);
  assert.deepEqual(r.place_params, { item: "place:50" });
  assert.equal(r.article, 1);
  assert.equal(r.door, 1);
  assert.equal(r.filter, 1);
  assert.equal(r.filter_params.field, "type");
  assert.equal(r.filter_params.value, "3");
  assert.ok(!JSON.stringify(r.filter_params).includes("SECRETNAME"));
  assert.equal(r.reset, 1);
  assert.equal(r.fav, 1);
  assert.equal(r.fav_on, true);
  assert.equal(r.fav_label, "В избранном");
  assert.equal(r.menu_open, 1);
  assert.equal(r.menu_nav, 1);
  assert.equal(r.faq, 1);
  assert.equal(r.faq_params.index, 2);
  assert.ok(!r.faq_params.question);
  assert.equal(r.diff, 1);
  assert.equal(r.gallery, 1);
  assert.equal(r.club, 1);
  assert.equal(r.club_nav_extra, 0);
  assert.deepEqual(r.review, { page_type: "place", page_id: "50", messenger: "max" });
  assert.equal(r.no_ym_threw, false);
  assert.equal(r.toc_without_ym, 0);
  assert.equal(r.invalid.field, "company");
  assert.equal(r.invalid_fetch, 0);
  assert.equal(r.http_error, 1);
  assert.equal(r.submit_before_ok, 0);
  assert.equal(r.submit, 1);
  assert.deepEqual(r.submit_params, { category: "adventure", subcategory: "rafting" });
  assert.equal(r.bot, 1);
  assert.equal(r.bot_max_click, 0);
  assert.equal(r.podbor_start, 1);
  assert.equal(r.podbor_q1, 1);
  assert.equal(r.podbor_q1_still, 1);
  assert.deepEqual(r.podbor_q1_params, { q: "season", answer: "winter", skipped: 0 });
  assert.equal(r.podbor_back, 1);
  assert.equal(r.podbor_error, 0);
  assert.ok(!r.payload.includes("SECRETNAME"));
  assert.ok(!r.payload.includes("+7900"));
  assert.ok(!r.payload.includes("a@b.c"));
  assert.ok(!r.payload.includes("plan_id"));
});
