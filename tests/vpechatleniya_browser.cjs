// Живой прогон /v: страница исполняется в Chrome, клики идут в настоящие обработчики.
// Запуск из корня репозитория: node tests/vpechatleniya_browser.cjs
const assert = require("node:assert");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const SHOTS = process.env.V_SHOTS || "/tmp/vpechatleniya-shots";
fs.mkdirSync(SHOTS, { recursive: true });

const EXPECTED = {
  adventure: 13, offroad: 9, guides: 17, animals_farms: 13,
  food: 10, stay: 10, rental: 12, transfer: 8,
};

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function startServer() {
  const port = 18000 + Math.floor(Math.random() * 2000);
  const logPath = "/tmp/vpechatleniya-serve.log";
  const log = fs.openSync(logPath, "w");
  const child = spawn(process.env.PYTHON || "python3", ["tests/vpechatleniya_serve.py"], {
    cwd: ROOT,
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", log, log],
  });
  const origin = "http://127.0.0.1:" + port;
  return (async () => {
    for (let i = 0; i < 50; i++) {
      try {
        const res = await fetch(origin + "/v");
        if (res.ok) return { child, origin, logPath };
      } catch (e) { /* ещё стартует */ }
      if (child.exitCode != null) break;
      await sleep(150);
    }
    const logText = fs.readFileSync(logPath, "utf8").slice(-800);
    throw new Error("server did not start\n" + logText);
  })();
}

async function launchChrome() {
  const debugPort = 9300 + Math.floor(Math.random() * 500);
  const chrome = spawn("google-chrome", [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--lang=ru-RU",
    "--window-size=1440,900",
    "--remote-debugging-port=" + debugPort,
    "about:blank",
  ], { stdio: "ignore" });
  let version;
  for (let i = 0; i < 40; i++) {
    try {
      const res = await fetch("http://127.0.0.1:" + debugPort + "/json/version");
      if (res.ok) { version = await res.json(); break; }
    } catch (e) { /* ещё стартует */ }
    await sleep(150);
  }
  if (!version) {
    chrome.kill("SIGKILL");
    throw new Error("devtools port did not open");
  }
  const ws = new WebSocket(version.webSocketDebuggerUrl);
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
  await send("Page.enable", {}, sessionId);
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: [
      "window.__net=[];",
      "const _fetch=window.fetch;",
      "window.fetch=function(){window.__net.push(String(arguments[0]));return _fetch.apply(this,arguments);};",
      "const _open=XMLHttpRequest.prototype.open;",
      "XMLHttpRequest.prototype.open=function(m,u){window.__net.push(m+' '+u);return _open.apply(this,arguments);};",
    ].join("\n"),
  }, sessionId);
  return {
    chrome, ws, send, sessionId,
    async stop() { try { ws.close(); } catch (e) {} chrome.kill("SIGKILL"); },
  };
}

async function evaluate(page, expression) {
  const ev = await page.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  }, page.sessionId);
  const details = ev.result && ev.result.exceptionDetails;
  if (details) {
    const desc = (details.exception && details.exception.description) || details.text || JSON.stringify(details);
    throw new Error(desc);
  }
  const inner = ev.result && ev.result.result;
  if (inner && inner.subtype === "error") throw new Error(inner.description || "eval error");
  return inner ? inner.value : undefined;
}

async function shot(page, name) {
  const ev = await page.send("Page.captureScreenshot", { format: "png" }, page.sessionId);
  const data = ev.result && ev.result.data;
  if (!data) throw new Error("no screenshot " + name + " " + JSON.stringify(ev).slice(0, 300));
  const file = path.join(SHOTS, name + ".png");
  fs.writeFileSync(file, Buffer.from(data, "base64"));
  return file;
}

async function setViewport(page, width, height, mobile) {
  const ev = await page.send("Emulation.setDeviceMetricsOverride", {
    width, height, deviceScaleFactor: 1, mobile: !!mobile,
  }, page.sessionId);
  if (ev.error) throw new Error(JSON.stringify(ev.error));
}

async function openPage(page, url) {
  const nav = await page.send("Page.navigate", { url }, page.sessionId);
  if (nav.error || (nav.result && nav.result.errorText)) {
    throw new Error("navigate " + JSON.stringify(nav).slice(0, 400));
  }
  await evaluate(page, `(async () => {
    const start = Date.now();
    while (Date.now() - start < 10000) {
      const cards = document.querySelectorAll(".catalog-grid .card").length;
      const thumbs = [...document.querySelectorAll(".category-sidebar img")];
      const covers = [...document.querySelectorAll(".catalog-grid .cover-img")].slice(0, 4);
      const ready = cards === 12 && document.querySelector("h1") && thumbs.length === 8
        && thumbs.every((img) => img.complete && img.naturalWidth > 0)
        && covers.every((img) => img.complete && img.naturalWidth > 0);
      if (ready) return true;
      await new Promise((r) => setTimeout(r, 80));
    }
    throw new Error("catalog not ready: " + (document.body ? document.body.innerText.slice(0, 240) : "no body"));
  })()`);
}

async function run() {
  const server = await startServer();
  const page = await launchChrome();
  const shots = [];
  try {
    await setViewport(page, 1440, 900, false);
    await openPage(page, server.origin + "/v");
    const initial = await evaluate(page, `(() => {
      const banner = document.getElementById("demo-disclaimer").innerText;
      const thumbs = [...document.querySelectorAll(".category-sidebar .category-photo")];
      const width = thumbs[0].getBoundingClientRect().width;
      const minibus = getComputedStyle(document.querySelector('.category-photo[data-photo="minibus"] img')).transform;
      if (document.title !== "Впечатления АдыГида") throw new Error("title " + document.title);
      const robots = document.querySelector('meta[name="robots"]').content.replace(/\\s/g, "");
      if (robots !== "noindex,nofollow") throw new Error("robots " + robots);
      if (!banner.includes("вымышлены") || !banner.includes("ориентировочн") || !banner.includes("иллюстратив")) throw new Error(banner);
      if (!banner.includes("не отправляются")) throw new Error(banner);
      if (document.querySelectorAll(".catalog-grid .card").length !== 12) throw new Error("cards");
      if (!document.querySelector(".result-count").textContent.includes("12 из 92")) throw new Error(document.querySelector(".result-count").textContent);
      if (document.body.getAttribute("data-menu-mode") !== "sidebar") throw new Error("menu mode");
      if (document.querySelector(".menu-explain")) throw new Error("changelog still shown");
      if (/Точечное обновление|Что изменено|\\bV7\\b|\\bV6\\b/.test(document.body.innerText)) throw new Error("internal note: " + document.body.innerText.slice(0, 180));
      if (!document.querySelector('[data-menu-mode="sidebar"]') || !document.querySelector('[data-menu-mode="panel"]')) throw new Error("menu switch missing");
      const photoKeys = [...document.querySelectorAll(".catalog-grid .cover-img")].map((img) => (img.src.match(/\\/photos\\/([a-z0-9]+)\\.webp/) || [])[1]);
      if (photoKeys.length !== 12 || photoKeys.some((key) => !key)) throw new Error("initial photos " + photoKeys.join(","));
      if (new Set(photoKeys).size !== 12) throw new Error("photo diversity " + photoKeys.join(","));
      for (let i = 1; i < photoKeys.length; i++) {
        if (photoKeys[i] === photoKeys[i - 1]) throw new Error("adjacent duplicate " + photoKeys.join(","));
      }
      for (const cols of [2, 3]) {
        for (let i = cols; i < photoKeys.length; i++) {
          if (photoKeys[i] === photoKeys[i - cols]) throw new Error("column duplicate " + cols + " " + photoKeys.join(","));
        }
      }
      if (!document.querySelector("h1").textContent.includes("Чем заняться")) throw new Error("h1");
      if (!document.querySelector(".eyebrow").textContent.includes("Впечатления АдыГида")) throw new Error("eyebrow");
      if (document.querySelector("form")) throw new Error("form");
      if (thumbs.length !== 8) throw new Error("thumbs " + thumbs.length);
      if (Math.abs(width - 52) > 1.5) throw new Error("thumb width " + width);
      if (!thumbs.every((box) => box.querySelector("img").alt && box.querySelector("img").naturalWidth > 0)) throw new Error("thumb alt");
      if (!minibus || minibus === "none") throw new Error("minibus zoom");
      if (document.querySelector('[data-menu-cat="thermal_relax"]')) throw new Error("thermal in menu");
      const cover = getComputedStyle(document.querySelector(".card .cover")).aspectRatio;
      if (cover.replace(/\\s/g, "") !== "16/11") throw new Error("ratio " + cover);
      return { banner: true, cards: 12, thumbWidth: width };
    })()`);
    shots.push(await shot(page, "v_desktop_catalog"));

    await evaluate(page, `(() => {
      const expected = ${JSON.stringify(EXPECTED)};
      document.querySelector('[data-menu-cat="adventure"]').click();
      const adventureIds = [...document.querySelectorAll(".catalog-grid .card")].slice(0, 3).map((card) => card.getAttribute("data-open"));
      if (adventureIds.join(",") !== "rafting-1,rafting-2,rafting-3") throw new Error("adventure order " + adventureIds.join(","));
      document.querySelector("#side-cat-food img").click();
      if (!document.querySelector(".result-count").textContent.includes("из 10")) throw new Error("food click " + document.querySelector(".result-count").textContent);
      for (const code of Object.keys(expected)) {
        document.querySelector('[data-menu-cat="' + code + '"]').click();
        const shown = document.querySelector(".result-count").textContent;
        const match = shown.match(/из (\\d+)/);
        const badge = document.querySelector('[data-menu-cat="' + code + '"] .section-count').textContent.trim();
        if (!match || Number(match[1]) !== expected[code]) throw new Error(code + " " + shown);
        if (badge !== String(expected[code])) throw new Error(code + " badge " + badge);
      }
      document.querySelector('[data-menu-cat="adventure"]').click();
      const sky = [...document.querySelectorAll(".subcategory-row")].find((b) => b.textContent.includes("Параплан"));
      if (!sky || !sky.disabled || !sky.textContent.includes("пока нет")) throw new Error("sky " + (sky && sky.textContent));
      document.querySelector("[data-menu-all]").click();
      if (!document.querySelector(".result-count").textContent.includes("из 92")) throw new Error("all");
      if (document.querySelector(".all-services .section-count").textContent.trim() !== "92") throw new Error("all badge");
      document.querySelector('[data-action="open-structure"]').click();
      if (document.querySelectorAll(".tax-cat").length !== 9) throw new Error("tax cats");
      if (document.querySelectorAll(".tax-subs span").length !== 48) throw new Error("tax subs");
      if (document.querySelectorAll(".tax-subs span.has").length !== 44) throw new Error("populated " + document.querySelectorAll(".tax-subs span.has").length);
      const text = document.querySelector(".overlay").innerText;
      if (!text.includes("отложено, не в продаже") || !text.includes("Термы и отдых") || !text.includes("без примеров")) throw new Error("structure copy");
      document.querySelector('[data-action="close-structure"]').click();
      if (document.querySelector(".overlay")) throw new Error("structure stayed");
    })()`);

    await evaluate(page, `(() => {
      document.querySelector('[data-action="reset"]').click();
      const input = document.getElementById("search-q");
      input.value = "сыр";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      const n = document.querySelectorAll(".catalog-grid .card").length;
      if (n < 2 || n > 8) throw new Error("cheese count " + n);
      if (!document.body.innerText.includes("Дегустация сыров")) throw new Error("cheese title missing");
      document.querySelector(".catalog-grid .card").click();
      document.getElementById("detail-bottom-back").click();
      if (document.getElementById("search-q").value !== "сыр") throw new Error("query lost");
      if (document.querySelectorAll(".catalog-grid .card").length !== n) throw new Error("count lost");
      document.querySelector('[data-action="reset"]').click();
      document.getElementById("family-toggle").click();
      if (!document.querySelector(".result-count").textContent.includes("из 56")) throw new Error(document.querySelector(".result-count").textContent);
      document.querySelector('[data-action="reset"]').click();
      document.querySelector('[data-action="more"]').click();
      if (!document.querySelector(".result-count").textContent.includes("24 из 92")) throw new Error(document.querySelector(".result-count").textContent);
      window.scrollTo(0, 720);
      const y = window.scrollY;
      if (y < 400) throw new Error("did not scroll " + y);
      document.querySelector(".catalog-grid .card").click();
      document.getElementById("detail-bottom-back").click();
      if (!document.querySelector(".result-count").textContent.includes("24 из 92")) throw new Error("shown lost");
      if (Math.abs(window.scrollY - y) > 30) throw new Error("scroll " + window.scrollY + " vs " + y);
    })()`);

    await evaluate(page, `(() => {
      function money(label) {
        const row = [...document.querySelectorAll(".money .row")].find((r) => r.firstElementChild.textContent === label);
        if (!row) throw new Error("no money row " + label);
        return Number(row.lastElementChild.textContent.replace(/\\D/g, ""));
      }
      document.querySelector('[data-go="catalog"]').click();
      document.querySelector('[data-action="reset"]').click();
      let input = document.getElementById("search-q");
      input.value = "Джиппинг по горным маршрутам";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      const jeep = document.querySelector('[data-open="jeep"]');
      if (!jeep) throw new Error("jeep missing");
      jeep.click();
      const related = [...document.querySelectorAll("#related-services .card")].map((c) => c.getAttribute("data-open"));
      if (related.length !== 4 || new Set(related).size !== 4 || related.includes("jeep")) throw new Error("related " + related.join(","));
      if (document.querySelectorAll("#related-services .card-relation").length !== 4) throw new Error("reasons");
      if (money("Условная стоимость услуги") !== 5000) throw new Error("subtotal");
      if (money("Сервисный сбор АдыГиду (5%)") !== 250) throw new Error("fee");
      if (money("Скидка организатора") !== 250) throw new Error("discount");
      if (money("Организатору на месте") !== 4750) throw new Error("onsite");
      if (money("Всего за поездку") !== 5000) throw new Error("total");
      if (!document.querySelector(".money").innerText.includes("после согласования")) throw new Error("fee timing");
      document.querySelector(".money").scrollIntoView({ block: "center" });
      const next = related[0];
      document.querySelector('#related-services [data-open="' + next + '"]').click();
      if (!document.querySelector('[data-action="detail-back"]')) throw new Error("no back");
      if (document.querySelector("h1").textContent.includes("Джиппинг по горным маршрутам")) throw new Error("did not open related");
      document.querySelector('[data-action="detail-back"]').click();
      if (!document.querySelector("h1").textContent.includes("Джиппинг по горным маршрутам")) throw new Error("back stack");
    })()`);
    shots.push(await shot(page, "v_desktop_detail_money"));

    await evaluate(page, `(() => {
      function money(label) {
        const row = [...document.querySelectorAll(".money .row")].find((r) => r.firstElementChild.textContent === label);
        if (!row) throw new Error("no money row " + label);
        return Number(row.lastElementChild.textContent.replace(/\\D/g, ""));
      }
      document.querySelector('[data-action="start-request"]').click();
      document.querySelector('[data-action="party-inc"]').click();
      if (money("Всего за поездку") !== 5000 || money("Сервисный сбор АдыГиду (5%)") !== 250 || money("Организатору на месте") !== 4750) {
        throw new Error("group price changed with party");
      }
      document.querySelector('[data-action="party-dec"]').click();
      document.querySelector('[data-action="submit"]').click();
      if (!document.body.innerText.includes("никуда не отправлена")) throw new Error("empty date was sent");
      if (!document.body.innerText.includes("ни письма, ни сообщения, ни записи в базу")) throw new Error("not-sent copy");
      const heading = [...document.querySelectorAll("h2")].find((h) => h.textContent.includes("никуда не отправлена"));
      if (heading) heading.scrollIntoView({ block: "center" });
    })()`);
    shots.push(await shot(page, "v_request_not_sent"));

    await evaluate(page, `(async () => {
      function money(label) {
        const row = [...document.querySelectorAll(".money .row")].find((r) => r.firstElementChild.textContent === label);
        if (!row) throw new Error("no money row " + label);
        return Number(row.lastElementChild.textContent.replace(/\\D/g, ""));
      }
      document.querySelector('[data-stage="form"]').click();
      const date = document.getElementById("wish-date");
      date.value = "не дата";
      date.dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-action="submit"]').click();
      if (!document.querySelector(".warn") || !document.querySelector(".warn").textContent.includes("Дату не разобрали")) throw new Error("invalid date");
      document.getElementById("wish-date").value = "1 января 2020";
      document.getElementById("wish-date").dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-action="submit"]').click();
      if (!document.querySelector(".warn") || !document.querySelector(".warn").textContent.includes("не раньше сегодняшней")) throw new Error("past date");
      const ahead = new Date();
      ahead.setDate(ahead.getDate() + 40);
      const iso = ahead.getFullYear() + "-" + String(ahead.getMonth() + 1).padStart(2, "0") + "-" + String(ahead.getDate()).padStart(2, "0");
      const dotted = String(ahead.getDate()).padStart(2, "0") + "." + String(ahead.getMonth() + 1).padStart(2, "0") + "." + ahead.getFullYear();
      document.getElementById("wish-date").value = iso;
      document.getElementById("wish-date").dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-action="submit"]').click();
      if (!document.body.innerText.includes("никуда не отправлена") || !document.body.innerText.includes(iso)) throw new Error("iso date");
      document.querySelector('[data-stage="form"]').click();
      document.getElementById("wish-date").value = dotted;
      document.getElementById("wish-date").dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-action="submit"]').click();
      if (!document.body.innerText.includes("никуда не отправлена")) throw new Error("dotted date");
      document.querySelector('[data-stage="form"]').click();
      document.querySelector('[data-action="fill-date"]').click();
      if (document.getElementById("wish-date").value !== "5 декабря 2026") throw new Error("example fill");
      document.querySelector('[data-action="submit"]').click();
      const exampleFuture = new Date(2026, 11, 5) >= new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
      if (exampleFuture && !document.body.innerText.includes("никуда не отправлена")) throw new Error("example date");
      if (!exampleFuture && !document.querySelector(".warn")) throw new Error("example past without warning");
      if (document.body.innerText.includes("никуда не отправлена")) {
        document.querySelector('[data-stage-fwd="offer"]').click();
        document.querySelector('[data-stage-fwd="pay"]').click();
        if (!document.body.innerText.includes("оплата не производится")) throw new Error("pay copy");
        if (!document.body.innerText.includes("Данные карты не запрашиваем")) throw new Error("card copy");
        if (document.querySelector('input[autocomplete="cc-number"], input[name="card"]')) throw new Error("card field");
      }
      document.querySelector('[data-go="catalog"]').click();
      document.querySelector('[data-action="reset"]').click();
      let input = document.getElementById("search-q");
      input.value = "Короткий сплав по горной реке";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-open="rafting-1"]').click();
      if (money("Условная стоимость услуги") !== 5600 || money("Сервисный сбор АдыГиду (5%)") !== 280 || money("Организатору на месте") !== 5320) {
        throw new Error("person price");
      }
      document.querySelector('[data-go="catalog"]').click();
      document.querySelector('[data-action="reset"]').click();
      input = document.getElementById("search-q");
      input.value = "Ночь в глэмпинге";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector('[data-open="glamp-1"]').click();
      document.querySelector('[data-action="start-request"]').click();
      if (money("Условная стоимость услуги") !== 8500) throw new Error("one night");
      document.querySelector('[data-action="nights-inc"]').click();
      if (money("Условная стоимость услуги") !== 17000 || money("Сервисный сбор АдыГиду (5%)") !== 850 || money("Организатору на месте") !== 16150) {
        throw new Error("two nights");
      }
    })()`);

    await evaluate(page, `(() => {
      document.querySelector('[data-go="catalog"]').click();
      document.querySelector('[data-action="reset"]').click();
      document.querySelector('[data-menu-mode="panel"]').click();
      if (document.body.getAttribute("data-menu-mode") !== "panel") throw new Error("panel mode");
      if (document.querySelector(".category-sidebar")) throw new Error("sidebar stayed");
      document.querySelector(".catalog-open").click();
      const boxes = [...document.querySelectorAll(".drawer-sections .category-photo")];
      if (boxes.length !== 8) throw new Error("panel thumbs " + boxes.length);
      const width = boxes[0].getBoundingClientRect().width;
      if (Math.abs(width - 68) > 1.5) throw new Error("panel width " + width);
      document.querySelector("#drawer-cat-adventure img").click();
      if (!document.querySelector(".result-count") && document.querySelector(".category-dialog")) {
        const row = document.querySelector('.drawer-subcategory-list [data-treesub="adventure:"]');
        if (row) row.click();
      }
      if (!document.querySelector(".result-count").textContent.includes("из 13")) throw new Error("panel pick " + (document.querySelector(".result-count") && document.querySelector(".result-count").textContent));
    })()`);

    const images = await evaluate(page, `(async () => {
      document.querySelector('[data-menu-mode="sidebar"]').click();
      document.querySelector("[data-menu-all]").click();
      let guard = 0;
      while (document.querySelector('[data-action="more"]') && guard < 20) {
        document.querySelector('[data-action="more"]').click();
        guard++;
      }
      if (document.querySelectorAll(".catalog-grid .card").length !== 92) throw new Error("loaded " + document.querySelectorAll(".catalog-grid .card").length);
      const imgs = [...document.querySelectorAll("img")];
      await Promise.all(imgs.map((img) => new Promise((resolve, reject) => {
        const ok = () => (img.naturalWidth > 0 ? resolve() : reject(new Error("zero " + img.alt + " " + img.src)));
        if (img.complete && img.naturalWidth > 0) return resolve();
        img.loading = "eager";
        img.addEventListener("load", ok, { once: true });
        img.addEventListener("error", () => reject(new Error("broken " + img.src)), { once: true });
        img.src = img.getAttribute("src");
      })));
      const keys = new Set(imgs.map((img) => {
        const m = img.src.match(/\\/photos\\/([a-z0-9]+)\\.webp/);
        return m ? m[1] : "";
      }).filter(Boolean));
      if (keys.size !== 39) throw new Error("unique photos " + keys.size + " of " + imgs.length);
      const hosts = [...new Set(performance.getEntriesByType("resource").map((e) => new URL(e.name).host))];
      if (hosts.some((h) => h !== location.host)) throw new Error("third party " + hosts.join(","));
      if ((window.__net || []).length) throw new Error("page requests " + window.__net.join(","));
      if (/рейтинг|★★|★/.test(document.body.innerText)) throw new Error("fake rating");
      return { cards: 92, photos: keys.size, images: imgs.length };
    })()`);

    await setViewport(page, 390, 844, true);
    await openPage(page, server.origin + "/v");
    shots.push(await shot(page, "v_mobile_catalog"));
    await evaluate(page, `(() => {
      const button = document.querySelector(".mobile-categories-button");
      if (getComputedStyle(button).display !== "flex") throw new Error("mobile button " + getComputedStyle(button).display);
      if (getComputedStyle(document.querySelector(".category-sidebar")).display !== "none") throw new Error("sidebar visible on mobile");
      button.click();
      const box = document.querySelector(".drawer-sections .category-photo");
      const width = box.getBoundingClientRect().width;
      if (Math.abs(width - 64) > 1.5) throw new Error("mobile thumb " + width);
      document.querySelector("#drawer-cat-food img").click();
      const dialog = document.querySelector(".category-dialog");
      if (!dialog || dialog.getAttribute("data-step") !== "subs") throw new Error("mobile step");
      if (getComputedStyle(document.querySelector(".drawer-subcategories")).display === "none") throw new Error("subs hidden");
      const row = document.querySelector('.drawer-subcategory-list [data-treesub="food:cheese"]');
      if (!row || row.disabled) throw new Error("cheese sub");
      row.click();
      const picked = document.querySelector(".result-count").textContent.match(/из (\\d+)/);
      if (!picked || Number(picked[1]) !== 2) throw new Error(document.querySelector(".result-count").textContent);
      if (document.querySelector(".category-dialog")) throw new Error("dialog stayed");
    })()`);
    await evaluate(page, `(() => { document.querySelector(".mobile-categories-button").click(); return true; })()`);
    shots.push(await shot(page, "v_mobile_categories"));

    const report = { ok: true, initial, images, shots, origin: server.origin };
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    return report;
  } finally {
    await page.stop();
    server.child.kill("SIGKILL");
  }
}

run().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
