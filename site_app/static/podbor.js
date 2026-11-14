/* Подбор маршрута. Логика оценок — в podbor-core.js, здесь только экран.
   Ответы уходят в /api/podbor/answers пакетом и не блокируют клики.
   Цели Метрики — через window.adygidGoal (обёртка goal в site.js). */
(function () {
  "use strict";
  const root = document.getElementById("podbor-root");
  const bootEl = document.getElementById("podbor-boot");
  if (!root || !bootEl || typeof window.PodborCore !== "function" && !window.PodborCore) return;
  const C = window.PodborCore;
  let boot = {};
  try { boot = JSON.parse(bootEl.textContent || "{}"); } catch (e) { boot = {}; }

  const DATA = Array.isArray(boot.items) ? boot.items : [];
  DATA.forEach((x) => {
    x.tags = x.tags || [];
    x.stops = x.stops || [];
    if (!x.visit) x.visit = { min: 60, typ: 90, max: 120, source: "estimate" };
  });
  const COPY = boot.copy || {};
  const REFINE_QUESTIONS = boot.refine || [];
  const SRC = boot.src || "direct";
  const AREA_NAMES = Object.fromEntries(Object.entries(C.AREAS).map(([k, v]) => [k, v[0]]));
  const LABELS = {
    views: "Виды и горы", water: "Водопады и ущелья", caves: "Пещеры и гроты",
    culture: "Культура и музеи", thermal: "Термы", familyfun: "Семейные развлечения",
  };
  const Q_GOAL = {
    season: "podbor_q1_done", duration: "podbor_q2_done", base: "podbor_q3_done",
    party: "podbor_q4_done", been: "podbor_q5_done", pace: "podbor_q6_done",
  };
  const QUESTIONS = [
    { key: "season", copy: "Сезон", title: "В какой сезон едете?", icon: "◌", why: "Сезон меняет впечатления, доступность троп и длину светового дня.", options: [["winter", "Ноябрь–декабрь", "Снежные виды, короткие дни и запасные идеи", "❄"], ["summer", "Лето", "Больше светлого времени и летних прогулок", "☀"], ["any", "Пока не определился", "Посмотреть разные варианты", "↗"]] },
    { key: "duration", copy: "Длительность", title: "Сколько дней на Адыгею?", icon: "◷", why: "Разложим места по дням с учётом времени на каждом месте и дороги.", options: [["one", "1 день", "Один насыщенный или спокойный день", "1"], ["short", "2–3 дня", "Можно сменить впечатления, не спеша", "3"], ["long", "4–7 дней", "Больше направлений и свободных пауз", "7"], ["any", "Пока не знаю", "Начнём с одного дня для примера", "↗"]] },
    { key: "base", copy: "Где остановились", title: "Где остановились?", icon: "⌂", why: "От базы считаем дорогу. Это мягкий приоритет, а не граница поездки.", options: [["maykop", "Майкоп", "", ""], ["khadzhokh", "Каменномостский (Хаджох)", "", ""], ["dakhovskaya", "Даховская", "", ""], ["guzeripl", "Гузерипль", "", ""], ["lago", "Лаго-Наки / Азишский перевал", "", ""], ["any", "Ещё не выбрали", "Можно определиться позже", "↗"]] },
    { key: "party", copy: "С кем едете", title: "С кем отправляетесь?", icon: "♧", why: "С малышами — короткие форматы и больше пауз. Возрастные правила объектов уточняются отдельно.", options: [["solo", "Один", "", ""], ["couple", "Вдвоём", "", ""], ["family", "Семья с детьми", "Детский интерес и посильные прогулки", ""], ["small", "С маленькими детьми", "Спокойные идеи, без длинных подъёмов", ""], ["any", "Неважно", "Состав поездки пока не учитываем", "↗"]] },
    { key: "been", copy: "Бывали в Адыгее", title: "Вы уже бывали в Адыгее?", icon: "✓", why: "Тем, кто здесь не впервые, добавим места не из каждого топа — и оставим пару самых лакомых.", options: [["first", "Нет, впервые", "Покажем лучшее Адыгеи", ""], ["some", "Был(а) 1–2 раза", "Меньше очевидного, больше нового", ""], ["often", "Часто бываю", "Хочу необычного", ""], ["any", "Пропустить", "Не учитываем", "↗"]] },
    { key: "pace", copy: "Темп", title: "В каком темпе отдыхаем?", icon: "≈", why: "Темп задаёт длину дня: ≈ 5,5 / 7,5 / 9,5 часа с дорогой — это оценка.", options: [["calm", "Спокойно", "", ""], ["balanced", "Сбалансированно", "", ""], ["active", "Активно", "", ""], ["any", "Не знаю", "", "↗"]] },
    { key: "interests", copy: "Что хочется увидеть", title: "Что хочется увидеть?", icon: "✳", why: "Выбранные темы всегда идут первыми. Остальное — отдельным блоком «Ещё может понравиться».", options: [["views", "Виды и горы", "", "△"], ["water", "Водопады и ущелья", "", "≋"], ["caves", "Пещеры и гроты", "", "◖"], ["culture", "Культура и музеи", "", "⌂"], ["thermal", "Термы", "", "♨"], ["familyfun", "Семейные развлечения", "", "◇"], ["any", "Удивите меня", "Разные стороны Адыгеи", "✧"]] },
  ];
  const MAIN_N = QUESTIONS.length;
  const STORE = "adygid_podbor_v1";
  const DIFF = { easy: "Лёгкая", medium: "Средняя", hard: "Сложная", extreme: "Экстремальная" };

  let SESSION = C.contextId();
  let state = fresh();
  let refining = false;
  let phase = 0;
  let lastKey = null;
  let lastAnswer = null;
  let lastUpdate = "";
  let busy = false;
  let timer = 0;
  let reviewOpen = false;
  let detailsOpen = false;
  let returnToReview = false;
  let pendingCapture = null;
  let started = false;
  let fewKey = "";
  let toastTimer = 0;
  const queue = [];
  let flushTimer = 0;

  function fresh() {
    return {
      step: 0, answers: {}, interests: [], final: false, tab: "all", limit: 6,
      days: null, seen: [], votes: {}, showAlt: false, planVote: null,
      planDensity: null, planReasons: [], planId: null,
    };
  }
  function goal(name, params) {
    try { if (typeof window.adygidGoal === "function") window.adygidGoal(name, params); } catch (e) { /* аналитика не роняет подбор */ }
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function copyLine(v, fallback) {
    if (Array.isArray(v)) return v.find((x) => typeof x === "string" && x.trim()) || fallback;
    return typeof v === "string" && v.trim() ? v : fallback;
  }
  function idx(key) { return QUESTIONS.findIndex((q) => q.key === key); }
  function answers() { return Object.assign({}, state.answers, { interests: state.interests }); }
  function rankNow() { return C.rankAll(DATA, answers(), { phase: phase, seen: new Set(state.seen), lastKey: lastKey, lastAnswer: lastAnswer }); }
  function keyOf(x) { return x.type + ":" + x.id; }
  function childrenTrip() { return ["small", "family"].includes(state.answers.party); }
  function markStart() {
    if (started) return;
    started = true;
    goal("podbor_start", { src: SRC });
  }
  function logEvent(type, fields, immediate) {
    const ev = C.makeEvent(SESSION, type, Object.assign({ plan_id: state.planId }, fields || {}));
    queue.push({
      event_type: String(ev.event_type || "").slice(0, 40),
      question_id: ev.question_id,
      answer_code: ev.answer_code,
      skipped: !!ev.skipped,
      item_key: ev.item_key,
      plan_id: ev.plan_id,
      algorithm_version: ev.algorithm_version,
    });
    if (immediate || queue.length >= 15) flush();
    else {
      clearTimeout(flushTimer);
      flushTimer = setTimeout(flush, 400);
    }
  }
  function flush() {
    clearTimeout(flushTimer);
    if (!queue.length) return;
    const batch = queue.splice(0, 40);
    const body = JSON.stringify({ session_id: SESSION, events: batch });
    try {
      if (navigator.sendBeacon) {
        const ok = navigator.sendBeacon("/api/podbor/answers", new Blob([body], { type: "application/json" }));
        if (ok) return;
      }
    } catch (e) { /* ниже fetch */ }
    fetch("/api/podbor/answers", {
      method: "POST",
      body: body,
      headers: { "Content-Type": "application/json" },
      keepalive: true,
    }).catch(() => {});
  }
  function persist() {
    try {
      sessionStorage.setItem(STORE, JSON.stringify({
        session: SESSION, step: state.step, answers: state.answers, interests: state.interests,
        final: state.final, seen: state.seen, votes: state.votes, planId: state.planId,
        planVote: state.planVote, planReasons: state.planReasons, planDensity: state.planDensity,
        days: state.days, tab: state.tab, showAlt: state.showAlt, refining: refining,
      }));
    } catch (e) { /* приватный режим */ }
  }
  function restore() {
    try {
      const data = JSON.parse(sessionStorage.getItem(STORE) || "null");
      if (!data || !/^[A-Za-z0-9_-]{8,64}$/.test(data.session || "")) return false;
      SESSION = data.session;
      state.step = Math.max(0, Math.min(QUESTIONS.length - 1, data.step | 0));
      state.answers = data.answers && typeof data.answers === "object" ? data.answers : {};
      state.interests = Array.isArray(data.interests) ? data.interests.filter((t) => LABELS[t]) : [];
      state.final = !!data.final;
      state.seen = Array.isArray(data.seen) ? data.seen.filter((k) => /^(place|route):\d+$/.test(k)) : [];
      state.votes = data.votes && typeof data.votes === "object" ? data.votes : {};
      state.planId = /^[A-Za-z0-9_-]{4,32}$/.test(data.planId || "") ? data.planId : null;
      state.planVote = data.planVote === "up" || data.planVote === "down" ? data.planVote : null;
      state.planReasons = Array.isArray(data.planReasons) ? data.planReasons.filter((r) => /^[a-z]{2,20}$/.test(r)) : [];
      state.planDensity = ["low", "ok", "high"].includes(data.planDensity) ? data.planDensity : null;
      state.days = data.days || null;
      state.tab = ["all", "route", "place"].includes(data.tab) ? data.tab : "all";
      state.showAlt = !!data.showAlt;
      if (data.refining && data.step >= MAIN_N) {
        refining = true;
        QUESTIONS.splice(MAIN_N, QUESTIONS.length - MAIN_N, ...REFINE_QUESTIONS.filter((q) => !q.children_only || childrenTrip()));
        state.step = Math.min(data.step, QUESTIONS.length - 1);
      }
      if (Object.keys(state.answers).length || state.interests.length) started = true;
      return true;
    } catch (e) { return false; }
  }
  function paceExplain(k) {
    const opt = QUESTIONS[idx("pace")].options.find((o) => o[0] === k);
    let v = (COPY.pace_explanations || {})[k] || (COPY.pace_explanations || {})[(opt && opt[1] || "").toLowerCase()] || "";
    if (typeof v === "object") v = Object.values(v).join(" ");
    const extra = { calm: " День ≈ 5,5 ч с дорогой, до 3 мест.", balanced: " День ≈ 7,5 ч с дорогой, до 4 мест.", active: " День ≈ 9,5 ч с дорогой, до 5 мест (зимой короче — светлое время)." }[k] || "";
    return v + extra;
  }
  function reaction(q, a) {
    const question = QUESTIONS.find((x) => x.key === q);
    const opt = question && question.options.find((o) => o[0] === a);
    const row = (COPY.reactions || {})[(question && question.copy) || q] || (COPY.reactions || {})[q] || {};
    const label = (opt && opt[1]) || "";
    let val = row[a] || row[label] || row[label.toLowerCase()];
    if (!val) {
      const found = Object.keys(row).find((k) => k.toLowerCase() === label.toLowerCase());
      if (found) val = row[found];
    }
    if (!val) val = row.any || ["Хорошо, обновляю идеи для вашей поездки 🧭"];
    const arr = (Array.isArray(val) ? val : [val]).filter((v) => typeof v === "string" && v.trim());
    return arr.length ? arr[Math.floor(Math.random() * arr.length)] : "Хорошо, обновляю идеи для вашей поездки 🧭";
  }
  function showToast(text) {
    clearTimeout(toastTimer);
    const el = document.getElementById("podbor-toast");
    el.textContent = text;
    el.classList.remove("hidden");
    toastTimer = setTimeout(() => el.classList.add("hidden"), 2400);
  }
  function reduced() { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
  /* Пауза между ответами была 1100 мс. Держим около 2 секунд (×2) и не дольше:
     ответ уже записан, оверлей только показывает кадр. */
  const REACTION_MS = 2200;
  const FLASH_MS = 750;
  const PLACE_PHOTOS = [];
  let reelGen = 0;
  let reelTimer = 0;
  let reelLayer = 0;
  function shuffle(list) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }
  function preloadPlacePhotos() {
    const seen = new Set();
    DATA.forEach((x) => {
      if (!x || x.type !== "place" || !x.image || seen.has(x.image)) return;
      seen.add(x.image);
      PLACE_PHOTOS.push({
        name: String(x.name || "Место Адыгеи"),
        image: String(x.image),
        ready: false,
        failed: false,
      });
    });
    const queue = shuffle(PLACE_PHOTOS);
    let inflight = 0;
    let cursor = 0;
    const pump = () => {
      while (inflight < 4 && cursor < queue.length) {
        const item = queue[cursor++];
        inflight += 1;
        const img = new Image();
        img.decoding = "async";
        img.onload = () => {
          item.ready = img.naturalWidth > 0;
          item.failed = !item.ready;
          inflight -= 1;
          pump();
        };
        img.onerror = () => {
          item.failed = true;
          inflight -= 1;
          pump();
        };
        img.src = item.image;
      }
    };
    pump();
  }
  function showSpinner() {
    const stage = document.getElementById("podbor-flash");
    const loader = document.getElementById("podbor-loader");
    if (stage) stage.classList.add("is-off");
    if (loader) loader.classList.remove("is-off");
  }
  function stopPhotoReel() {
    reelGen += 1;
    clearTimeout(reelTimer);
    const stage = document.getElementById("podbor-flash");
    if (stage) {
      stage.classList.add("is-off");
      stage.querySelectorAll("img").forEach((img) => img.classList.remove("is-on"));
    }
    const loader = document.getElementById("podbor-loader");
    if (loader) loader.classList.remove("is-off");
  }
  function paintFrame(photo, gen) {
    return new Promise((resolve) => {
      const stage = document.getElementById("podbor-flash");
      const loader = document.getElementById("podbor-loader");
      if (!stage || !loader) { resolve(false); return; }
      const imgs = stage.querySelectorAll("img");
      const incoming = imgs[reelLayer % 2];
      const outgoing = imgs[(reelLayer + 1) % 2];
      let settled = false;
      const finish = (ok) => {
        if (settled) return;
        settled = true;
        incoming.onload = null;
        incoming.onerror = null;
        resolve(ok);
      };
      const show = () => {
        if (gen !== reelGen) { finish(false); return; }
        const cap = document.getElementById("podbor-flash-cap");
        if (cap) cap.textContent = photo.name;
        incoming.classList.add("is-on");
        if (outgoing) outgoing.classList.remove("is-on");
        stage.classList.remove("is-off");
        loader.classList.add("is-off");
        reelLayer += 1;
        finish(true);
      };
      const fail = () => {
        photo.ready = false;
        photo.failed = true;
        if (!stage.querySelector("img.is-on")) showSpinner();
        finish(false);
      };
      incoming.onload = () => {
        if (!incoming.naturalWidth) { fail(); return; }
        if (typeof incoming.decode === "function") incoming.decode().then(show).catch(show);
        else show();
      };
      incoming.onerror = fail;
      const abs = new URL(photo.image, window.location.href).href;
      if (incoming.src === abs && incoming.complete) {
        if (incoming.naturalWidth) incoming.onload();
        else fail();
        return;
      }
      incoming.src = photo.image;
    });
  }
  function startPhotoReel() {
    stopPhotoReel();
    const gen = reelGen;
    if (reduced()) return;
    const arm = () => {
      if (gen !== reelGen) return;
      const pool = PLACE_PHOTOS.filter((p) => p.ready && !p.failed);
      if (!pool.length) {
        showSpinner();
        if (PLACE_PHOTOS.some((p) => !p.ready && !p.failed)) reelTimer = setTimeout(arm, 160);
        return;
      }
      const order = shuffle(pool);
      let i = 0;
      const step = () => {
        if (gen !== reelGen) return;
        const photo = order[i % order.length];
        i += 1;
        paintFrame(photo, gen).then((ok) => {
          if (gen !== reelGen) return;
          if (!ok) {
            const left = shuffle(PLACE_PHOTOS.filter((p) => p.ready && !p.failed));
            if (left.length) {
              order.splice(0, order.length, ...left);
              i = 0;
              step();
              return;
            }
            showSpinner();
            if (PLACE_PHOTOS.some((p) => !p.ready && !p.failed)) reelTimer = setTimeout(arm, 160);
            return;
          }
          if (order.length > 1) reelTimer = setTimeout(step, FLASH_MS);
        });
      };
      step();
    };
    arm();
  }
  function holdReaction(text, done) {
    busy = true;
    const el = document.getElementById("podbor-reaction");
    document.getElementById("podbor-reaction-text").textContent = text;
    el.classList.add("show");
    startPhotoReel();
    const wait = reduced() ? 0 : REACTION_MS;
    timer = setTimeout(() => {
      el.classList.remove("show");
      stopPhotoReel();
      busy = false;
      if (typeof done === "function") done();
    }, wait);
  }
  function animateAnswer(q, a, done) {
    const text = q === "summary" ? copyLine(COPY.summary, "Готово, пожелания собраны ✅")
      : q === "final" ? copyLine(refining ? (COPY.refine_final || COPY.final) : COPY.final, "Собираю план поездки 🧭")
      : reaction(q, a);
    holdReaction(text, done);
  }
  function scrollWizard() {
    if (window.innerWidth < 900) document.getElementById("wizard").scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
  }
  function answerLabel(q) {
    if (q.key === "interests") return state.interests.length ? state.interests.map((t) => LABELS[t]).join(" + ") : "Удивите меня";
    const hit = q.options.find((o) => o[0] === (state.answers[q.key] || "any"));
    return (hit && hit[1]) || "Не указано";
  }
  function why(x) {
    const arr = [];
    const matched = state.interests.filter((t) => x.tags.includes(t));
    if (matched.length) arr.push("Тема «" + LABELS[matched[0]].toLowerCase() + "»");
    if (x.editorial === "best" && state.answers.been === "first") arr.push("Из лучшего в Адыгее");
    if (x.editorial === "unusual" && ["some", "often"].includes(state.answers.been)) arr.push("Не из каждого топа");
    if (x.editorial === "best" && state.answers.been === "often") arr.push("Одно из лакомых");
    if (state.answers.base && state.answers.base === x.area) arr.push("Рядом с базой");
    if (state.answers.pace === "calm" && x.difficulty === "easy") arr.push("Лёгкий уровень по карточке");
    if (childrenTrip() && x.kid) arr.push("Отметка «с детьми»; ограничения уточняются");
    if (!arr.length) arr.push(x.type === "route" ? "Готовый маршрут автора" : "Место из подборки АдыГида");
    return arr.slice(0, 2).join(" · ");
  }
  function costLine(x) {
    if (x.is_paid === true) return "Стоимость: платно" + (x.price_note ? " · " + x.price_note : "");
    if (x.is_paid === false) return "Стоимость: бесплатно";
    return "Стоимость: уточняем, скоро появится :)";
  }
  function vt(x) {
    const v = x.visit;
    const known = v.source === "card";
    return '<span class="podbor-time' + (known ? " is-card" : "") + '">⏱ ≈ ' + esc(C.fmtRange(v)) + " · " + (known ? "по данным сайта" : "оценка") + "</span>";
  }
  function acts(x) {
    const k = keyOf(x);
    const v = state.votes[k];
    return '<div class="podbor-acts"><button type="button" data-act="vote" data-k="' + k + '" data-v="up" class="' + (v === "up" ? "on" : "") + '" aria-label="Нравится">👍</button><button type="button" data-act="vote" data-k="' + k + '" data-v="down" class="bad ' + (v === "down" ? "on" : "") + '" aria-label="Не нравится">👎</button><button type="button" data-act="seen" data-k="' + k + '">✓ Уже был тут</button></div>';
  }
  function moreLink(x, block, pos) {
    const label = x.type === "route" ? "Читать маршрут" : "Подробнее о месте";
    return '<a class="podbor-source" href="' + esc(x.url) + '" target="_blank" rel="noopener" data-act="open" data-item="' + keyOf(x) + '" data-pos="' + pos + '" data-block="' + block + '">' + label + " ↗</a>";
  }
  function card(x, block, pos) {
    const photo = x.image ? '<img src="' + esc(x.image) + '" alt="' + esc(x.name) + '" loading="lazy">' : "";
    const diff = DIFF[x.difficulty] ? "<span>" + DIFF[x.difficulty] + " · по карточке</span>" : "";
    const winter = state.answers.season === "winter" && x.winter_ok === "unknown" ? "<span>Зимой — уточнить подход</span>" : "";
    const because = block === "also" ? "Не из выбранных тем — для разнообразия" : why(x);
    return '<article class="podbor-card' + (block === "also" ? " is-also" : "") + '" data-type="' + x.type + '" data-id="' + x.id + '"><div class="podbor-photo">' + photo + '<span class="podbor-badge">' + (x.type === "route" ? "Маршрут" : "Место") + "</span><span class=\"podbor-area\">" + esc(AREA_NAMES[x.area] || "Адыгея") + '</span></div><div class="podbor-cardbody"><h3>' + esc(x.name) + '</h3><div class="podbor-why">' + esc(because) + '</div><div class="podbor-facts">' + vt(x) + diff + winter + "</div>" + acts(x) + moreLink(x, block === "also" ? "also" : "main", pos) + '<details><summary>Что проверить перед поездкой</summary><p>Режим, подход и условия на дату. Время на месте и в дороге — ориентир (≈), не обещание.</p><p>' + esc(costLine(x)) + "</p></details></div></article>";
  }
  function summary() {
    return QUESTIONS.map((q, i) => {
      if (state.answers[q.key] === undefined && !(q.key === "interests" && state.answers.interests !== undefined)) return "";
      return '<button type="button" class="podbor-chip" data-act="edit" data-i="' + i + '">' + esc(answerLabel(q)) + " ↗</button>";
    }).join("");
  }
  /* Визуал A2. Ключи ответов и подписи o[1] не меняются: по ним ищутся
     реакции в podbor_copy.json. Короткие подписи ниже — только на карточках. */
  const IMG_V = (root.dataset && root.dataset.asset) || "";
  const TICK = '<i class="a2-tick" aria-hidden="true">✓</i>';
  const VISUAL = {
    season: {
      title: "Когда едете?", hint: "От сезона зависят тропы и длина дня", tile: "Сезон",
      opts: {
        winter: { sub: "снег, горы, термы", ti: "❄️", img: "winter", tone: "winter" },
        summer: { sub: "водопады и луга", ti: "☀️", img: "summer", tone: "summer" },
        any: { sub: "покажем разное", ti: "🗓️", img: "anyseason", tone: "any" },
      },
    },
    duration: {
      title: "Сколько дней?", hint: "Разложим места по дням с дорогой", tile: "Дней",
      opts: {
        one: { sub: "один яркий день", n: 1 },
        short: { sub: "без спешки", n: 3 },
        long: { sub: "много направлений", n: 7 },
        any: { sub: "начнём с одного", n: 0 },
      },
    },
    base: {
      title: "Где остановились?", hint: "От базы считаем дорогу", tile: "База",
      opts: {
        maykop: { img: "maykop" },
        khadzhokh: { label: "Хаджох", img: "khadzhokh" },
        dakhovskaya: { img: "dakhovskaya" },
        guzeripl: { img: "guzeripl" },
        lago: { label: "Лаго-Наки", img: "lago" },
        any: { emoji: "📍" },
      },
    },
    party: {
      title: "С кем едете?", hint: "С малышами — короче прогулки, больше пауз", tile: "С кем",
      credits: ["Max Dawncat, CC BY 2.0", "vastateparksstaff, CC BY 2.0", "NPS/Patrick Myers, CC BY 2.0"],
      opts: {
        solo: { emoji: "🧍", img: "who_solo" },
        couple: { emoji: "👫", img: "who_couple" },
        family: { emoji: "👨‍👩‍👧", img: "who_family" },
        small: { label: "С малышами", emoji: "👶", img: "who_small" },
        any: { emoji: "🤷" },
      },
    },
    been: {
      title: "Уже бывали в Адыгее?", hint: "Бывалым — меньше очевидного", tile: "Бывали",
      opts: {
        first: { label: "Впервые", sub: "покажем лучшее", ti: "🌱", pins: 0, cards: ["khadzhokh"] },
        some: { label: "1–2 раза", sub: "больше нового", ti: "🔁", pins: 2, cards: ["lago", "khadzhokh", "water"] },
        often: { sub: "хочу необычного", ti: "🧭", pins: 9, cards: ["caves", "views", "pv_slon", "lago", "water", "khadzhokh"] },
        any: {},
      },
    },
    pace: {
      title: "Какой темп?", hint: "Задаёт длину дня", tile: "Темп",
      opts: {
        calm: { sub: "виды, кафе, без спешки", ti: "🌿", lvl: 1, hrs: "≈5,5 ч", img: "pace_calm" },
        balanced: { sub: "прогулки + отдых", ti: "🥾", lvl: 2, hrs: "≈7,5 ч", img: "pace_bal" },
        active: { sub: "тропы, рафтинг", ti: "⚡", lvl: 3, hrs: "≈9,5 ч", img: "pace_act" },
        any: { ti: "🤔" },
      },
    },
    interests: {
      title: "Что хочется увидеть?", hint: "Можно выбрать несколько", tile: "Хочется увидеть",
      credits: ["R. Laubenstein (USFWS), PD"],
      opts: {
        any: { sub: "разные стороны Адыгеи", emoji: "✨" },
        views: { label: "Горы и виды", img: "views" },
        water: { label: "Водопады", img: "water" },
        caves: { label: "Пещеры", img: "caves" },
        culture: { label: "Культура", img: "culture" },
        thermal: { img: "thermal" },
        familyfun: { label: "Для детей", img: "familyfun" },
      },
    },
    /* Доп. вопросы после плана: тот же язык фото-карточек. pid — id места в каталоге:
       берём его обложку, img — запасной кадр из /assets/podbor. */
    childage: {
      hint: "Чтобы осторожнее выбирать нагрузку", tile: "Возраст детей", kind: "photo2",
      credits: ["NPS/Patrick Myers, CC BY 2.0", "vastateparksstaff, CC BY 2.0", "R. Laubenstein (USFWS), PD", "NPS, PD"],
      opts: {
        tiny: { label: "До 3 лет", img: "who_small" },
        preschool: { label: "3–6 лет", img: "who_family" },
        school: { label: "7–11 лет", img: "familyfun" },
        teen: { label: "12–17 лет", img: "age_teen" },
        any: {},
      },
    },
    walking: {
      title: "Сколько готовы ходить?", hint: "Уберём лишние подъёмы и лестницы", tile: "Прогулки", kind: "banners",
      opts: {
        short: { label: "Коротко", sub: "вышли, посмотрели, дальше", pid: 42, img: "views", lvl: 1 },
        stepfree: { label: "Без ступеней", sub: "коляска, ровные дорожки", pid: 71, img: "maykop", lvl: 1 },
        long: { label: "Можно дольше", sub: "длинные тропы — да", pid: 46, img: "pace_bal", lvl: 3 },
        any: {},
      },
    },
    distance: {
      title: "Далеко ли ездить?", hint: "Сгруппируем идеи вокруг базы", tile: "Направления", kind: "maps",
      opts: {
        local: { label: "Рядом с базой", sub: "свой район", ring: 1 },
        adjacent: { label: "И соседние", sub: "чуть шире", ring: 2 },
        wide: { label: "Куда угодно", sub: "вся Адыгея", ring: 3 },
        any: {},
      },
    },
    rain: {
      title: "Если пойдёт дождь?", hint: "Погоду не обещаем — подготовим запасной вариант", tile: "Непогода", kind: "banners",
      opts: {
        backup: { label: "Запасная идея", sub: "одна крытая точка про запас", pid: 45, img: "pv_belov", lvl: 2 },
        indoor: { label: "Музейный день", sub: "под крышей, часы уточнить", pid: 83, img: "culture", lvl: 1 },
        outdoors: { label: "Гуляем всё равно", sub: "по фактической погоде", img: "pace_bal", lvl: 3 },
        any: {},
      },
    },
    exclude: {
      title: "Чего точно не хочется?", hint: "Уберём тему из мест и маршрутов", tile: "Исключить", kind: "nope",
      opts: {
        thermal: { label: "Без терм", img: "thermal" },
        culture: { label: "Без музеев", pid: 69, img: "culture" },
        cable: { label: "Без канатки", pid: 48, img: "dakhovskaya" },
        any: { label: "Ничего не исключать" },
      },
    },
  };
  /* Карта Адыгеи (OSM, упрощённый контур) для карточек «Бывали» и «Далеко ли ездить». */
  const MAP_PATH = "M2.0 20.2 L5.6 20.5 L6.8 19.1 L7.0 20.7 L9.9 22.1 L10.4 24.2 L21.9 29.5 L24.9 28.2 L34.9 30.0 L39.8 29.4 L41.2 30.3 L41.1 29.3 L44.8 30.2 L45.3 28.7 L44.8 28.1 L49.4 25.5 L48.6 25.2 L48.8 24.1 L45.5 22.0 L45.6 20.9 L42.1 19.1 L42.9 17.8 L41.7 18.6 L40.7 17.7 L40.5 14.4 L42.4 14.4 L43.1 13.1 L44.1 13.1 L43.4 13.9 L44.6 13.7 L44.1 14.6 L44.7 14.8 L46.0 13.1 L47.9 13.5 L49.4 14.6 L48.6 15.7 L49.6 15.9 L46.8 18.1 L47.8 19.6 L50.6 17.3 L50.3 18.3 L51.3 18.2 L50.7 18.7 L51.5 19.1 L50.8 19.4 L51.3 20.2 L55.3 18.7 L54.8 17.6 L60.8 15.3 L62.7 21.9 L63.6 21.7 L64.6 24.3 L63.2 24.9 L64.3 27.7 L65.2 27.4 L65.7 28.6 L63.4 28.8 L63.7 30.0 L64.3 31.1 L65.5 30.6 L67.8 34.3 L65.8 36.3 L63.6 35.0 L62.0 36.6 L62.8 38.4 L61.3 40.1 L62.3 40.9 L61.7 41.5 L62.5 42.6 L62.2 43.8 L63.1 44.2 L62.9 45.1 L60.2 45.0 L60.5 55.9 L59.7 57.1 L60.5 58.4 L58.8 61.3 L60.0 62.4 L61.3 61.5 L62.6 62.4 L64.5 61.7 L65.3 63.2 L65.1 66.7 L65.9 67.7 L69.4 67.2 L71.0 68.7 L70.1 69.8 L70.7 73.3 L69.8 75.6 L70.9 76.7 L70.0 77.2 L69.1 76.2 L67.2 78.3 L67.3 79.6 L65.8 80.4 L64.7 78.4 L61.3 77.0 L59.8 73.0 L55.1 72.9 L55.4 74.0 L54.7 75.4 L58.1 80.2 L56.4 84.4 L56.5 85.8 L57.5 86.7 L55.5 88.2 L57.0 90.2 L59.1 90.8 L62.1 89.8 L61.9 87.4 L62.6 87.5 L67.0 93.6 L68.5 93.8 L70.9 96.2 L71.5 94.8 L73.8 95.4 L75.6 94.4 L77.0 100.8 L78.7 102.0 L81.4 100.6 L84.6 100.9 L85.0 98.0 L86.9 93.8 L86.1 92.8 L86.4 89.8 L89.9 88.0 L86.6 81.2 L87.6 77.8 L86.2 76.5 L86.3 74.1 L84.0 68.7 L90.0 63.9 L87.7 56.7 L86.5 56.6 L85.2 52.8 L87.2 50.3 L86.7 48.9 L83.5 48.0 L82.9 46.6 L83.7 44.6 L83.2 41.3 L84.9 42.0 L86.1 40.6 L86.2 39.3 L84.3 38.3 L84.3 36.4 L87.4 35.1 L87.4 33.2 L92.2 33.2 L91.8 34.7 L94.0 34.5 L94.2 40.6 L96.7 40.7 L96.7 41.9 L97.9 41.9 L97.9 45.5 L99.2 48.1 L98.7 52.4 L96.7 52.4 L96.7 53.7 L104.4 53.6 L101.8 47.3 L102.3 43.8 L98.3 38.3 L97.4 32.3 L95.1 28.7 L95.2 26.3 L92.5 23.7 L92.2 21.5 L85.4 14.6 L80.3 12.6 L80.8 11.0 L80.1 9.8 L78.6 10.2 L77.5 8.8 L73.3 8.5 L70.8 9.3 L70.8 10.1 L70.0 9.3 L69.6 10.4 L61.2 11.1 L61.5 10.3 L60.1 9.2 L58.8 9.5 L56.6 7.9 L54.1 7.8 L53.0 6.5 L51.7 6.8 L50.7 5.4 L51.0 3.5 L47.6 2.0 L44.2 3.9 L43.8 5.8 L42.6 5.8 L39.7 8.5 L40.1 9.9 L39.0 9.3 L38.2 10.7 L37.2 10.5 L35.9 13.0 L33.4 13.8 L33.2 14.8 L31.2 15.8 L30.8 14.8 L30.3 16.7 L28.7 15.7 L28.3 17.7 L23.2 17.0 L20.9 18.6 L19.5 17.9 L18.6 19.1 L18.2 16.6 L15.2 17.0 L15.2 14.5 L12.6 15.4 L12.5 13.2 L10.3 14.9 L10.6 16.8 L8.5 16.0 L8.0 17.2 L5.5 14.6 L6.1 13.0 L3.9 14.1 L2.7 12.3 L2.0 20.2Z";
  const MAP_P = { lon0: 38.6840182, lat1: 45.2168098, k: 0.712026, s: 68.71996 };
  function mapXY(lat, lon) {
    return [((lon - MAP_P.lon0) * MAP_P.k * MAP_P.s + 2).toFixed(1), ((MAP_P.lat1 - lat) * MAP_P.s + 2).toFixed(1)];
  }
  /* Точки «бывал»: реальные координаты, разнесённые по всей республике. */
  const PIN_SPOTS = [[44.295, 40.185], [44.085, 40.015], [44.605, 40.1], [45.03, 38.93], [44.807, 39.947], [44.89, 40.5], [44.417, 40.346], [44.0, 40.136], [44.174, 40.3]];
  function pinSvg(pt, i) {
    const [x, y] = mapXY(pt[0], pt[1]);
    return '<g class="a3-pin" transform="translate(' + x + " " + y + ')"><path d="M0 0c-3.2-4-5-6.3-5-8.7a5 5 0 0 1 10 0c0 2.4-1.8 4.7-5 8.7Z"/><circle cx="0" cy="-8.6" r="1.9"/></g>';
  }
  function mapSvg(inner, cls) {
    return '<svg class="a3-map' + (cls ? " " + cls : "") + '" viewBox="0 0 107 104" aria-hidden="true"><path class="a3-land" d="' + MAP_PATH + '"/>' + inner + "</svg>";
  }
  function beenMap(v) {
    if (!v.pins) {
      const [x, y] = mapXY(44.295, 40.185);
      return mapSvg('<g class="a3-start" transform="translate(' + x + " " + y + ')"><circle r="9"/><circle r="3.4"/></g>');
    }
    const spots = PIN_SPOTS.slice(0, v.pins);
    const route = v.pins > 2 ? '<path class="a3-trail" d="M' + [3, 4, 2, 6, 0, 1].map((k) => mapXY(spots[k][0], spots[k][1]).join(" ")).join(" L") + '"/>' : "";
    return mapSvg(route + spots.map(pinSvg).join(""));
  }
  function distMap(v) {
    const b = C.baseAnchor(state.answers.base) || { lat: 44.29, lon: 40.18 };
    const [x, y] = mapXY(b.lat, b.lon);
    const r = { 1: 9, 2: 20, 3: 0 }[v.ring];
    const zone = v.ring === 3
      ? '<path class="a3-zone a3-zone-all" d="' + MAP_PATH + '"/>'
      : '<circle class="a3-zone" cx="' + x + '" cy="' + y + '" r="' + r + '"/>';
    return mapSvg(zone + '<circle class="a3-base" cx="' + x + '" cy="' + y + '" r="3.2"/>');
  }
  function postcards(v) {
    return '<span class="a3-cards a3-cards-' + v.cards.length + '">' + v.cards.map((n, i) => '<span class="a3-pcard" style="--i:' + i + '">' + photoTag(n, "lazy") + "</span>").join("") + "</span>";
  }
  const BEEN_VARIANT = /[?&]been=map\b/.test(window.location.search) ? "map" : "cards";
  /* Имена и кадры — как в прототипе. id мест живого каталога (в engine.js их нет,
     там только подписи и файлы). Обложка и ссылка берутся из каталога, если место есть. */
  const PREVIEW = {
    views: [
      { id: 105, name: "Скала Слон", img: "pv_slon", area: "Каменномостский" },
      { id: 55, name: "Плато Лаго-Наки", img: "lago", area: "Лаго-Наки" },
      { id: 56, name: "Каменное море", img: "views", area: "Лаго-Наки" },
    ],
    water: [
      { id: 24, name: "Хаджохская теснина", img: "khadzhokh", area: "Хаджох" },
      { id: 40, name: "Водопады Руфабго", img: "water", area: "Хаджох" },
    ],
    caves: [
      { id: 25, name: "Большая Азишская пещера", img: "caves", area: "Лаго-Наки" },
      { id: 60, name: "Пещера Нежная", img: "pv_nezh", area: "Хамышки" },
    ],
    culture: [
      { id: 51, name: "Дегуакская поляна дольменов", img: "culture", area: "Даховская" },
      { id: 45, name: "Музей «Беловодье»", img: "pv_belov", area: "Хаджох" },
    ],
    thermal: [
      { id: 68, name: "«Кедровый бор»", img: "thermal", area: "Цветочный" },
      { id: 67, name: "«АкваТермо»", img: "pv_aqua", area: "Тульский" },
    ],
    familyfun: [
      { id: 48, name: "Савранская канатка", img: "dakhovskaya", area: "Даховская" },
      { id: 43, name: "Экстрим-парк «Мишоко»", img: "pv_mishoko", area: "Каменномостский" },
    ],
  };
  function pimg(name) {
    return "/assets/podbor/" + name + ".webp" + (IMG_V ? "?v=" + encodeURIComponent(IMG_V) : "");
  }
  function photoTag(name, mode) {
    if (!name) return "";
    const extra = mode === "high" ? ' fetchpriority="high"' : (mode === "eager" ? "" : ' loading="lazy"');
    return '<img src="' + esc(pimg(name)) + '" alt="" decoding="async"' + extra + ">";
  }
  function catalogImage(id) {
    const hit = id && DATA.find((x) => x && x.type === "place" && Number(x.id) === Number(id));
    return (hit && hit.image) || "";
  }
  function optPhoto(v, mode) {
    const src = catalogImage(v.pid);
    if (!src) return photoTag(v.img, mode);
    const fb = v.img ? pimg(v.img) : "";
    return '<img src="' + esc(src) + '" alt="" decoding="async"' + (mode === "lazy" ? ' loading="lazy"' : "") + (fb ? ' data-fallback="' + esc(fb) + '"' : "") + ">";
  }
  function visOf(q, id) {
    return (VISUAL[q.key] && VISUAL[q.key].opts[id]) || {};
  }
  function shownLabel(q, id) {
    const v = visOf(q, id);
    if (v.label) return v.label;
    const hit = q.options.find((o) => o[0] === id);
    return (hit && hit[1]) || "";
  }
  function chosen(q, id) {
    if (q.key === "interests") {
      if (id === "any") return state.interests.length === 0 && state.answers.interests !== undefined;
      return state.interests.includes(id);
    }
    return state.answers[q.key] === id;
  }
  function btnOpen(q, id, cls) {
    const on = chosen(q, id);
    return '<button type="button" class="' + cls + (on ? " is-on" : "") + '" data-act="choose" data-q="' + q.key + '" data-answer="' + id + '" aria-pressed="' + on + '">';
  }
  function stepChrome(pos, total, count) {
    const pct = Math.round(((pos + 1) / total) * 100);
    return '<header class="a2-bar"><span class="a2-brand"><span class="a2-mark" aria-hidden="true">▲</span>АдыГид</span><span class="a2-count">' + esc(count || ((pos + 1) + " / " + total)) + '</span></header><div class="a2-prog" aria-hidden="true"><i style="width:' + pct + '%"></i></div>';
  }
  function navHtml(atStart) {
    return '<nav class="a2-nav"><button type="button" class="a2-btn-ghost" data-act="back"' + (atStart ? " disabled" : "") + '>← Назад</button><button type="button" class="a2-skip" data-act="skip">Пропустить</button></nav>';
  }
  function creditsHtml(v) {
    if (!v || !v.credits || !v.credits.length) return "";
    return '<p class="a2-credits">Фото: ' + esc(v.credits.join("; ")) + " · Wikimedia Commons</p>";
  }
  function pill(q, o) {
    const v = visOf(q, o[0]);
    return btnOpen(q, o[0], "a2-pill") + (v.emoji ? v.emoji + " " : "") + esc(shownLabel(q, o[0])) + "</button>";
  }
  function seasonOpts(q) {
    return '<div class="a2-banners">' + q.options.map((o, i) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a2-sb a2-sb-" + (v.tone || "any")) + photoTag(v.img, i === 0 ? "high" : "eager") + '<span class="a2-shade"></span><span class="a2-sb-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + (v.emoji ? '<span class="a2-emoji">' + v.emoji + "</span>" : "") + TICK + "</button>";
    }).join("") + "</div>";
  }
  function daysOpts(q) {
    return '<div class="a2-tl-list">' + q.options.map((o) => {
      const v = visOf(q, o[0]);
      const n = v.n || 0;
      const cells = Array.from({ length: 7 }, (_, i) => '<i class="' + (n && i < n ? "f" : "") + '"></i>').join("");
      const bar = '<span class="a2-tl-bar' + (n ? "" : " a2-tl-q") + '">' + cells + "</span>";
      return btnOpen(q, o[0], "a2-tl") + '<span class="a2-tl-top"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + bar + TICK + "</button>";
    }).join("") + "</div>";
  }
  function baseOpts(q) {
    return '<div class="a2-mini3">' + q.options.map((o) => {
      const v = visOf(q, o[0]);
      const ph = v.img
        ? '<span class="a2-mc-ph">' + photoTag(v.img, "lazy") + "</span>"
        : '<span class="a2-mc-ph a2-mc-em">' + (v.emoji || "") + "</span>";
      return btnOpen(q, o[0], "a2-mc" + (v.img ? "" : " a2-mc-any")) + ph + "<b>" + esc(shownLabel(q, o[0])) + "</b>" + TICK + "</button>";
    }).join("") + "</div>";
  }
  function photo2Opts(q) {
    const photos = q.options.filter((o) => visOf(q, o[0]).img);
    const rest = q.options.filter((o) => !visOf(q, o[0]).img);
    return '<div class="a2-ph2">' + photos.map((o) => {
      return btnOpen(q, o[0], "a2-pc") + photoTag(visOf(q, o[0]).img, "lazy") + '<span class="a2-shade"></span><b>' + esc(shownLabel(q, o[0])) + "</b>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function photo3Opts(q) {
    const photos = q.options.filter((o) => visOf(q, o[0]).img);
    const rest = q.options.filter((o) => !visOf(q, o[0]).img);
    return '<div class="a2-ph3">' + photos.map((o) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a2-pc a2-pc-v") + photoTag(v.img, "lazy") + '<span class="a2-shade"></span><span class="a2-pc-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function beenOpts(q) {
    const opts = q.options.filter((o) => o[0] !== "any");
    const rest = q.options.filter((o) => o[0] === "any");
    return '<div class="a2-ph3 a3-been a3-been-' + BEEN_VARIANT + '">' + opts.map((o) => {
      const v = visOf(q, o[0]);
      const art = BEEN_VARIANT === "cards" ? postcards(v) : beenMap(v);
      return btnOpen(q, o[0], "a3-vc") + '<span class="a3-vc-art">' + art + '</span><span class="a3-vc-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function mapsOpts(q) {
    const opts = q.options.filter((o) => o[0] !== "any");
    const rest = q.options.filter((o) => o[0] === "any");
    return '<div class="a2-ph3 a3-been a3-been-map">' + opts.map((o) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a3-vc") + '<span class="a3-vc-art">' + distMap(v) + '</span><span class="a3-vc-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function refBanners(q) {
    const opts = q.options.filter((o) => o[0] !== "any");
    const rest = q.options.filter((o) => o[0] === "any");
    return '<div class="a2-banners a2-pace a3-ref">' + opts.map((o) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a2-sb a2-sb-pace a2-sb-l" + (v.lvl || 2)) + optPhoto(v, "lazy") + '<span class="a2-shade"></span><span class="a2-sb-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + "</small></span>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function refPhoto2(q) {
    const opts = q.options.filter((o) => o[0] !== "any");
    const rest = q.options.filter((o) => o[0] === "any");
    return '<div class="a2-ph2">' + opts.map((o) => btnOpen(q, o[0], "a2-pc") + optPhoto(visOf(q, o[0]), "lazy") + '<span class="a2-shade"></span><b>' + esc(shownLabel(q, o[0])) + "</b>" + TICK + "</button>").join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function nopeOpts(q) {
    const opts = q.options.filter((o) => o[0] !== "any");
    const rest = q.options.filter((o) => o[0] === "any");
    return '<div class="a2-mini3 a3-nope">' + opts.map((o) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a2-mc") + '<span class="a2-mc-ph">' + optPhoto(v, "lazy") + '<span class="a3-x" aria-hidden="true"></span></span><b>' + esc(shownLabel(q, o[0])) + "</b>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function paceOpts(q) {
    const photos = q.options.filter((o) => visOf(q, o[0]).img);
    const rest = q.options.filter((o) => !visOf(q, o[0]).img);
    return '<div class="a2-banners a2-pace">' + photos.map((o) => {
      const v = visOf(q, o[0]);
      const bars = [1, 2, 3].map((i) => '<i class="' + (i <= v.lvl ? "f" : "") + '"></i>').join("");
      return btnOpen(q, o[0], "a2-sb a2-sb-pace a2-sb-l" + v.lvl) + photoTag(v.img, "lazy") + '<span class="a2-shade"></span><span class="a2-sb-txt"><b>' + esc(shownLabel(q, o[0])) + "</b><small>" + esc(v.sub || "") + '</small></span><span class="a2-lvl">' + bars + "<em>" + esc(v.hrs || "") + "</em></span>" + TICK + "</button>";
    }).join("") + "</div>" + rest.map((o) => pill(q, o)).join("");
  }
  function interestsOpts(q) {
    const any = q.options.find((o) => o[0] === "any");
    const rest = q.options.filter((o) => o[0] !== "any");
    const vAny = visOf(q, any[0]);
    const mosaic = '<span class="a2-mosaic">' + ["s2", "water", "caves", "s3"].map((n) => photoTag(n, "lazy")).join("") + "</span>";
    const top = btnOpen(q, any[0], "a2-surprise") + mosaic + '<span class="a2-sp-txt"><b>' + vAny.emoji + " " + esc(shownLabel(q, any[0])) + "</b><small>" + esc(vAny.sub || "") + "</small></span>" + TICK + "</button>";
    const grid = '<div class="a2-mini3 a2-ints">' + rest.map((o) => {
      const v = visOf(q, o[0]);
      return btnOpen(q, o[0], "a2-mc") + '<span class="a2-mc-ph">' + photoTag(v.img, "lazy") + "</span><b>" + esc(shownLabel(q, o[0])) + "</b>" + TICK + "</button>";
    }).join("") + "</div>";
    return top + '<div class="a2-or"><span>или выберите темы</span></div>' + grid;
  }
  function renderRefine(q) {
    const list = QUESTIONS.slice(MAIN_N);
    const pos = Math.max(0, state.step - MAIN_N);
    const vis = VISUAL[q.key];
    if (vis && vis.kind) {
      const body = { photo2: refPhoto2, banners: refBanners, maps: mapsOpts, nope: nopeOpts }[vis.kind](q);
      return stepChrome(pos, Math.max(1, list.length), "уточнение " + (pos + 1) + " / " + list.length) + '<main class="a2-q"><p class="a2-kicker">Уточнение · необязательно</p><h1>' + esc(vis.title || q.title || q.copy) + '</h1><p class="a2-hint">' + esc(vis.hint || q.why || "") + '</p><div class="a2-opts">' + body + "</div>" + creditsHtml(vis) + "</main>" + navHtml(false);
    }
    const rows = q.options.map((o) => {
      return btnOpen(q, o[0], "a2-row" + (o[0] === "any" ? " a2-row-quiet" : "")) + '<span class="a2-row-txt"><b>' + esc(o[1]) + "</b>" + (o[2] ? "<small>" + esc(o[2]) + "</small>" : "") + "</span>" + TICK + "</button>";
    }).join("");
    return stepChrome(pos, Math.max(1, list.length), "уточнение " + (pos + 1) + " / " + list.length) + '<main class="a2-q"><p class="a2-kicker">Уточнение</p><h1>' + esc(q.title || q.copy) + '</h1><p class="a2-hint">' + esc(q.why || "") + '</p><div class="a2-opts"><div class="a2-rows">' + rows + "</div></div></main>" + navHtml(false);
  }
  function renderA2(q) {
    const v = VISUAL[q.key];
    const body = { season: seasonOpts, duration: daysOpts, base: baseOpts, party: photo2Opts, been: beenOpts, pace: paceOpts, interests: interestsOpts }[q.key](q);
    const n = state.interests.length;
    const cta = q.key === "interests"
      ? '<div class="a2-sticky"><button type="button" class="a2-btn" data-act="finish">' + (n ? "Готово · " + n + " ✓" : "Дальше") + " →</button></div>"
      : "";
    return stepChrome(state.step, MAIN_N) + '<main class="a2-q"><h1>' + esc(v.title) + '</h1><p class="a2-hint">' + esc(v.hint) + '</p><div class="a2-opts">' + body + "</div>" + creditsHtml(v) + "</main>" + cta + navHtml(state.step === 0);
  }
  function tileIcon(q) {
    if (q.key === "interests") return state.interests.length ? "📸" : "✨";
    const id = state.answers[q.key] || "any";
    const v = visOf(q, id);
    if (v.ti) return v.ti;
    if (v.emoji) return v.emoji;
    if (q.key === "duration") return "📅";
    if (q.key === "base") return "🏡";
    return "•";
  }
  function tileValue(q) {
    if (q.key === "interests") {
      if (!state.interests.length) return "Удивите меня";
      return state.interests.map((t) => shownLabel(q, t) || LABELS[t]).join(", ");
    }
    const id = state.answers[q.key] || "any";
    return shownLabel(q, id) || "Не указано";
  }
  function flowSummary() {
    const parts = [];
    ["season", "duration", "party"].forEach((k) => {
      const id = state.answers[k];
      if (!id || id === "any") return;
      const q = QUESTIONS[idx(k)];
      const v = visOf(q, id);
      const label = shownLabel(q, id).toLowerCase();
      if (!label) return;
      parts.push((v.emoji ? v.emoji + " " : "") + label);
    });
    return parts.length ? parts.join(" · ") : "Осталось нажать одну кнопку";
  }
  function previewPlaces() {
    let keys = state.interests.filter((k) => PREVIEW[k]);
    if (!keys.length) keys = ["water", "views", "caves", "thermal"];
    const lists = keys.map((k) => PREVIEW[k].slice());
    const out = [];
    while (out.length < 4 && lists.some((l) => l.length)) {
      lists.forEach((l) => { if (l.length && out.length < 4) out.push(l.shift()); });
    }
    return out.map((spec) => {
      const live = DATA.find((x) => x && x.type === "place" && Number(x.id) === spec.id);
      const fallback = pimg(spec.img);
      return {
        name: spec.name,
        area: spec.area,
        url: (live && live.url) || ("/mesta/" + spec.id),
        image: (live && live.image) || fallback,
        fallback: fallback,
      };
    });
  }
  function renderPreview() {
    const cards = previewPlaces().map((x) => {
      return '<a class="a2-pv" href="' + esc(x.url) + '"><img src="' + esc(x.image) + '" alt="" width="112" height="112" loading="lazy" decoding="async" data-fallback="' + esc(x.fallback) + '"><b>' + esc(x.name) + "</b><small>" + esc(x.area) + "</small></a>";
    }).join("");
    const tiles = detailsOpen
      ? '<div class="a2-params">' + QUESTIONS.map((q, i) => '<button type="button" class="a2-param" data-act="edit" data-i="' + i + '"><span class="a2-p-ic">' + tileIcon(q) + '</span><span class="a2-p-t"><small>' + esc((VISUAL[q.key] && VISUAL[q.key].tile) || q.copy) + "</small><b>" + esc(tileValue(q)) + '</b></span><span class="a2-p-ed" aria-hidden="true">✎</span></button>').join("") + "</div>"
      : "";
    const toggle = detailsOpen ? "Скрыть детали ▴" : "Изменить детали";
    return '<section class="a2-fin"><div class="a2-hero"><img src="' + esc(pimg("hero")) + '" alt="" decoding="async" loading="lazy"><span class="a2-hero-shade"></span><header class="a2-bar a2-bar-light"><span class="a2-brand"><span class="a2-mark" aria-hidden="true">▲</span>АдыГид</span></header><div class="a2-fin-copy"><span class="a2-kick">Всё готово</span><h1>План по Адыгее<br>почти собран</h1><p>' + esc(flowSummary()) + '</p></div></div><div class="a2-sheet"><div class="a2-pv-head"><h2>Например, вас ждут:</h2><small>подберём ещё и разложим по дням</small></div><div class="a2-pv-row">' + cards + '</div><div class="a2-final-btns"><button type="button" class="a2-btn" data-act="confirm">Сформировать план →</button><button type="button" class="a2-btn-ghost' + (detailsOpen ? " is-on" : "") + '" data-act="details">' + toggle + "</button></div>" + tiles + "</div></section>";
  }
  function wizard() {
    if (reviewOpen && !state.final) return renderPreview();
    const q = QUESTIONS[state.step] || QUESTIONS[0];
    if (state.final) return "";
    if (refining && state.step >= MAIN_N) return renderRefine(q);
    if (VISUAL[q.key]) return renderA2(q);
    return renderRefine(q);
  }
  function hiddenBar() {
    return state.seen.length ? '<div class="podbor-hidden">Скрыто как «уже был»: ' + state.seen.length + ' <button type="button" data-act="unseen">вернуть все</button></div>' : "";
  }
  function modeNotice(R) {
    const ints = state.interests.map((t) => LABELS[t]).join(" + ");
    const exc = R.excluded.filter((e) => C.interestCount(e.x, state.interests) > 0);
    const reasons = [...new Set(exc.flatMap((e) => e.reasons))].slice(0, 3).join("; ");
    const whyHtml = exc.length ? "<details><summary>Почему другие места по этой теме не включены?</summary><p>" + exc.slice(0, 5).map((e) => esc(e.x.name) + ": " + esc(e.reasons[0])).join("<br>") + "</p></details>" : "";
    if (R.mode === "none") {
      return '<div class="podbor-notice"><b>По теме «' + esc(ints) + '» с вашими условиями совпадений нет.</b><p>' + esc(reasons || "В базе пока нет подходящей карточки") + '. Не подменяем тему молча.</p><div class="podbor-nav"><button type="button" class="podbor-btn podbor-btn-ghost" data-act="edit" data-i="' + idx("interests") + '">Изменить интересы</button><button type="button" class="podbor-btn podbor-btn-ghost" data-act="alt">' + (state.showAlt ? "Скрыть похожие идеи" : "Показать похожие идеи") + "</button></div>" + whyHtml + "</div>";
    }
    if (R.mode === "few") {
      return '<div class="podbor-notice"><b>По теме «' + esc(ints) + "» нашлось только " + R.main.length + ".</b><p>" + (reasons ? "Часть мест убрана: " + esc(reasons) + ". " : "") + 'Честно показываем, что есть, и не добиваем план случайными местами.</p><div class="podbor-nav"><button type="button" class="podbor-btn podbor-btn-ghost" data-act="edit" data-i="' + idx("interests") + '">Добавить интерес</button><button type="button" class="podbor-btn podbor-btn-ghost" data-act="alt">' + (state.showAlt ? "Скрыть похожие идеи" : "Показать похожие идеи") + "</button></div>" + whyHtml + "</div>";
    }
    return whyHtml;
  }
  function altBlock(R) {
    if (!state.showAlt || !["few", "none"].includes(R.mode)) return "";
    const shown = new Set(R.also.map((z) => keyOf(z.x)));
    const alt = R.alternatives.filter((z) => !shown.has(keyOf(z.x)));
    return alt.length ? '<div class="podbor-alsohead"><span>Похожие идеи</span><h3>Не по выбранной теме</h3></div><div class="podbor-cards">' + alt.map((z, i) => card(z.x, "also", i)).join("") + "</div>" : "";
  }
  function alsoBlock(R) {
    if (!R.also.length) return "";
    return '<div class="podbor-alsohead"><span>Не по выбранным темам</span><h3>Ещё может понравиться</h3><p>Не больше четверти выдачи. Выбранные темы всегда выше.</p></div><div class="podbor-cards" id="also-cards">' + R.also.map((z, i) => card(z.x, "also", i)).join("") + "</div>";
  }
  function liveResults() {
    const R = rankNow();
    noteFew(R);
    const list = R.main.map((z) => z.x);
    const routes = list.filter((x) => x.type === "route").length;
    const sel = state.tab === "all" ? list : list.filter((x) => x.type === state.tab);
    const tabs = [["all", "Всё", list.length], ["route", "Маршруты", routes], ["place", "Места", list.length - routes]].map(([k, t, c]) => '<button type="button" class="podbor-tab' + (state.tab === k ? " is-on" : "") + '" data-act="tab" data-t="' + k + '">' + t + " · " + c + "</button>").join("");
    return '<div class="podbor-chips">' + summary() + '</div><div class="podbor-results-head"><div><div class="podbor-kicker">Уже под ваши ответы</div><h2>' + (state.interests.length ? "По вашим интересам" : "Места и маршруты") + '</h2></div><span class="podbor-live">Обновляется сразу</span></div><p class="podbor-count">' + (list.length - routes) + " мест · " + routes + " маршрутов" + (R.also.length ? " · ещё " + R.also.length + " не по теме ниже" : "") + "</p>" + (lastUpdate ? '<div class="podbor-update" role="status">' + esc(lastUpdate) + "</div>" : "") + hiddenBar() + '<div class="podbor-tabs">' + tabs + "</div>" + modeNotice(R) + '<div class="podbor-cards" id="main-cards">' + sel.slice(0, state.limit).map((x, i) => card(x, "main", i)).join("") + "</div>" + (sel.length > state.limit ? '<button type="button" class="podbor-btn podbor-btn-ghost" data-act="more">Показать ещё</button>' : "") + alsoBlock(R) + altBlock(R) + '<p class="podbor-fine">Подбираем опубликованные карточки, а не подтверждаем доступ на вашу дату. Стоимость: уточняем, скоро появится :)</p>';
  }
  function noteFew(R) {
    if (R.mode !== "few" && R.mode !== "none") return;
    const key = R.mode + "|" + state.interests.join(",");
    if (key === fewKey) return;
    fewKey = key;
    goal("podbor_result_few", { mode: R.mode, interests: state.interests.join(",") });
  }
  /* Короткое имя для карточки плана: полное — в title/alt.
     «Посёлок: что посмотреть» → вторая часть (посёлок уже в шапке дня);
     «Место: пояснение» → само место; дальше срезаем хвост «в Майкопе» и
     перечисления. Остальное добирает обрезка в две строки в CSS. */
  const CTX_PREFIX = /^(Победа|Каменномостский|Гузерипль|Хамышки|Тульский|Хаджох|Новосвободная|Даховская|Уна-Коз понизу|Равнинная Адыгея|Лаго-Наки летом)$/;
  function shortName(name) {
    let t = String(name || "").replace(/\s*\([^)]*\)/g, "").trim();
    if (t.length <= 38) return t;
    const ci = t.indexOf(":");
    if (ci > 0) {
      const l = t.slice(0, ci).trim();
      const r = t.slice(ci + 1).trim();
      t = CTX_PREFIX.test(l) && r ? r.charAt(0).toUpperCase() + r.slice(1) : l;
    }
    if (t.length > 36 && t.indexOf(" — ") > 0) {
      const parts = t.split(" — ");
      t = /^«[^»]+»$/.test(parts[1]) ? "«" + parts[1].charAt(1).toUpperCase() + parts[1].slice(2) : parts[0];
    }
    if (t.length > 40) {
      const cut = t.replace(/\s(по дороге\s)?(в|у|на|над|под)\s\S+(\s\S+)?$/, "");
      if (cut.length >= 15) t = cut;
    }
    if (t.length > 42) {
      const m = t.slice(12).search(/,\s|\sи\s|\s\+\s/);
      if (m >= 0) t = t.slice(0, 12 + m);
    }
    return t;
  }
  function stopId(x) { return "stop-" + x.type + "-" + x.id; }
  /* Карточка точки дня: фото с названием — ссылка на карточку места/маршрута,
     текст ниже не кликается (чтобы не промахиваться мимо 👍/👎). */
  function stopRow(z, i) {
    const x = z.x;
    const link = ' href="' + esc(x.url) + '" title="' + esc(x.name) + '" target="_blank" rel="noopener" data-act="open" data-item="' + keyOf(x) + '" data-pos="' + i + '" data-block="plan"';
    const photo = x.image ? '<img src="' + esc(x.image) + '" alt="' + esc(x.name) + '" loading="lazy" decoding="async">' : "";
    const kind = x.type === "route" ? "маршрут" : "место";
    const drive = z.drive == null ? "" : '<span class="a3-drive">' + (z.drive === 0 ? "рядом с базой" : (i === 0 ? "от базы" : "в дороге") + " <b>≈ " + esc(C.fmtMin(z.drive)) + "</b> <em>(по расчёту сайта)</em>") + "</span>";
    const winter = state.answers.season === "winter" && x.winter_ok === "unknown" ? '<p class="a3-warn">Зимой уточнить подход</p>' : "";
    const also = z.kind === "also" ? '<span class="a3-also">по пути, не из ваших тем</span>' : "";
    const v = x.visit;
    const known = v.source === "card";
    return '<article class="a3-stop' + (z.kind === "also" ? " is-also" : "") + '" id="' + stopId(x) + '" data-type="' + x.type + '" data-id="' + x.id + '"><a class="a3-stop-ph"' + link + ">" + photo + '<span class="a3-stop-shade"></span><span class="a3-stop-n">' + (i + 1) + '</span><span class="a3-stop-cap"><h4>' + esc(shortName(x.name)) + '</h4></span></a><div class="a3-stop-body"><p class="a3-why">' + esc(why(x)) + "</p>" + winter + '<p class="a3-stop-meta"><span class="a3-kind">⏱ ≈ ' + esc(C.fmtRange(v)) + " на месте" + (known ? "" : " (оценка)") + " · " + kind + "</span>" + drive + also + "</p>" + '<div class="a3-stop-acts">' + acts(x).replace(">✓ Уже был тут<", ">✓ Был тут<") + '<a class="a3-more"' + link + ">" + (x.type === "route" ? "Маршрут" : "Подробнее") + " ↗</a></div></div></article>";
  }
  const NOTE_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h8l4 4v12.5A1.5 1.5 0 0 1 17.5 21h-11A1.5 1.5 0 0 1 5 19.5v-15A1.5 1.5 0 0 1 6.5 3Z"/><path d="M15 3v4h4M8.5 11h7M8.5 14.5h7M8.5 18h4"/></svg>';
  function clubBlock(afterOnly) {
    const url = boot.club || "/klub";
    return '<aside class="a3-club"><div class="a3-club-txt"><b>Часы и цены иногда меняются</b><p>Спросите тех, кто сейчас в Адыгее, — подскажут в АдыГид клубе.</p></div><a class="a3-club-btn" href="' + esc(url) + '" target="_blank" rel="noopener" data-act="club"><img src="/assets/magnet-max.png" alt="" width="22" height="22">Спросить в клубе MAX</a></aside>';
  }
  function yandexDayUrl(day) {
    const pts = [];
    (day.stops || []).forEach((z) => {
      const x = z && z.x;
      if (!x) return;
      const lat = Number(x.lat);
      const lon = Number(x.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      pts.push([Math.round(lat * 1e6) / 1e6, Math.round(lon * 1e6) / 1e6]);
    });
    if (pts.length >= 2) return "https://yandex.ru/maps/?rtext=" + pts.map((p) => p[0] + "," + p[1]).join("~") + "&rtt=auto";
    if (pts.length === 1) return "https://yandex.ru/maps/?pt=" + pts[0][1] + "," + pts[0][0] + "&z=14";
    return "";
  }
  function dayHtml(d, i) {
    if (d.empty) return '<section class="podbor-day"><div class="podbor-dayhead"><span>День ' + (i + 1) + '</span><h3>Свободный день</h3></div><p>Больше подходящих мест под ваши интересы и условия не нашлось. Не добиваем день случайными местами — можно отдохнуть или изменить пожелания.</p></section>';
    const vp = Math.round(d.visitMin / d.budget * 100);
    const dp = Math.round(d.driveMin / d.budget * 100);
    const word = d.stops.length === 1 ? "точка" : d.stops.length < 5 ? "точки" : "точек";
    const mapUrl = yandexDayUrl(d);
    const mapBtn = mapUrl ? '<a class="podbor-yamaps" href="' + esc(mapUrl) + '" target="_blank" rel="noopener" data-act="yamaps" data-day="' + (i + 1) + '">Открыть день в Яндекс Картах</a>' : "";
    const toc = '<ol class="a3-toc">' + d.stops.map((z, k) => '<li><a href="#' + stopId(z.x) + '" data-act="toc" data-target="' + stopId(z.x) + '"><i>' + (k + 1) + "</i>" + esc(z.x.name) + "</a></li>").join("") + "</ol>";
    return '<section class="podbor-day a3-day" id="day-' + (i + 1) + '"><div class="podbor-dayhead"><span>День ' + (i + 1) + "</span><div><h3>" + esc(AREA_NAMES[d.area] || "Адыгея") + '</h3><p>' + d.stops.length + " " + word + " · ≈ " + esc(C.fmtMin(d.totalMin)) + " с дорогой</p></div></div>" + toc + '<div class="podbor-bud" aria-hidden="true"><i class="is-visit" style="width:' + Math.min(100, vp) + '%"></i><i class="is-drive" style="width:' + Math.min(100 - Math.min(100, vp), dp) + '%"></i></div><p class="podbor-bud-label">на местах · дорога · запас. Светлое время ≈ ' + esc(C.fmtMin(d.daylight)) + "</p>" + '<div class="a3-stops">' + d.stops.map(stopRow).join("") + "</div>" + (d.returnDrive != null ? '<p class="a3-return">обратно на базу <b>≈ ' + esc(C.fmtMin(d.returnDrive)) + "</b></p>" : "") + (d.long ? '<p class="podbor-daynote">Длинный выход — на весь день, другие точки не добавляем.</p>' : "") + mapBtn + "</section>";
  }
  function planCode() {
    if (!state.planId || !/^[A-Za-z0-9_-]{4,32}$/.test(state.planId)) state.planId = C.contextId();
    return state.planId;
  }
  function feedback() {
    const reasons = [["far", "Далеко ехать"], ["dense", "Слишком насыщенно"], ["interests", "Не те интересы"], ["been", "Уже был в этих местах"], ["other", "Другое"]];
    let fix = "";
    if (state.planReasons.includes("dense")) fix += '<div class="podbor-fix">Сделать день спокойнее? <button type="button" class="podbor-btn podbor-btn-ghost" data-act="fix" data-f="calm">Пересобрать в спокойном темпе</button></div>';
    if (state.planReasons.includes("far")) {
      fix += '<div class="podbor-fix">' + (C.baseAnchor(state.answers.base)
        ? 'Оставить только район базы? <button type="button" class="podbor-btn podbor-btn-ghost" data-act="fix" data-f="local">Только рядом с базой</button>'
        : 'Укажите базу — посчитаем дорогу от неё. <button type="button" class="podbor-btn podbor-btn-ghost" data-act="edit" data-i="' + idx("base") + '">Выбрать базу</button>') + "</div>";
    }
    if (state.planReasons.includes("interests")) fix += '<div class="podbor-fix"><button type="button" class="podbor-btn podbor-btn-ghost" data-act="edit" data-i="' + idx("interests") + '">Изменить интересы</button></div>';
    if (state.planReasons.includes("been")) fix += '<div class="podbor-fix">Отметьте «✓ Был тут» на карточках — заменим их. Или <button type="button" class="podbor-btn podbor-btn-ghost" data-act="fix" data-f="often">покажите необычное</button></div>';
    const down = state.planVote === "down"
      ? '<div class="podbor-q">Что не так? Можно несколько</div><div class="podbor-row">' + reasons.map(([k, t]) => '<button type="button" data-act="reason" data-r="' + k + '" class="' + (state.planReasons.includes(k) ? "on" : "") + '">' + t + "</button>").join("") + "</div>" + fix
      : "";
    const density = state.planVote
      ? '<div class="podbor-q">Насколько насыщенные дни?</div><div class="podbor-row">' + [["low", "Можно больше"], ["ok", "В самый раз"], ["high", "Слишком много"]].map(([k, t]) => '<button type="button" data-act="density" data-d="' + k + '" class="' + (state.planDensity === k ? "on" : "") + '">' + t + "</button>").join("") + "</div>"
      : "";
    const href = "https://max.ru/se15002131_bot?start=podbor_" + planCode();
    return '<div class="podbor-feedback" id="feedback"><h3>Подошёл маршрут?</h3><div class="podbor-row"><button type="button" data-act="pv" data-v="up" class="' + (state.planVote === "up" ? "on" : "") + '">👍 Да</button><button type="button" data-act="pv" data-v="down" class="' + (state.planVote === "down" ? "on" : "") + '">👎 Не совсем</button></div>' + down + density + '<p class="podbor-q">Не нравится конкретное место — нажмите на карточке 👎 или «✓ Был тут».</p><a class="podbor-max" href="' + href + '" target="_blank" rel="noopener" data-act="bot">Дать обратную связь</a></div>';
  }
  function finalResults() {
    const R = rankNow();
    noteFew(R);
    const days = C.planDays(R, answers(), { days: state.days });
    const dur = state.answers.duration;
    const opts = dur === "short" ? [2, 3] : dur === "long" ? [4, 5, 6, 7] : [1];
    const dayBtns = opts.length > 1 ? '<div class="podbor-daycount">Сколько дней показать? ' + opts.map((n) => '<button type="button" class="podbor-tab' + (C.daysFor(answers(), state.days) === n ? " is-on" : "") + '" data-act="days" data-n="' + n + '">' + n + "</button>").join("") + "</div>" : "";
    const n = days.length;
    const dword = n === 1 ? "день" : n < 5 ? "дня" : "дней";
    const daysHtml = days.map((d, i) => dayHtml(d, i) + (i === 0 ? clubBlock() : "")).join("");
    return '<div class="a3-plan-top"><div class="podbor-kicker">Ваш план</div><h2 class="podbor-final-title">' + n + " " + dword + ' по Адыгее</h2><button type="button" class="a3-share" data-act="share">' + NOTE_ICON + '<span>Сохранить план<small>ссылкой — откроется на любом устройстве</small></span></button>' + dayBtns + "</div>" + (R.mode === "few" || R.mode === "none" ? modeNotice(R) : "") + hiddenBar() + daysHtml + (R.mode === "few" || R.mode === "none" ? "" : modeNotice(R)) + altBlock(R) + feedback() + '<div class="podbor-again"><h3>Хотите подстроить ещё точнее?</h3><p>Возраст детей, ходьба, непогода, что исключить. Всё необязательно.</p><div class="podbor-nav"><button type="button" class="podbor-btn" data-act="refine">Сделать точнее — ещё пара вопросов</button><button type="button" class="podbor-btn podbor-btn-ghost" data-act="enough">Достаточно</button></div></div><p class="podbor-fine">Ничего не забронировано. Подборка не обещает безопасность или выполнимость. Стоимость: уточняем, скоро появится :)</p>';
  }
  const SHARE_ORDER = ["season", "duration", "base", "party", "been", "pace"];
  const REFINE_KEYS = ["childage", "walking", "distance", "rain", "exclude"];
  const SHARE_VALUES = {
    season: ["winter", "summer", "any"],
    duration: ["one", "short", "long", "any"],
    base: ["maykop", "khadzhokh", "dakhovskaya", "guzeripl", "lago", "any"],
    party: ["solo", "couple", "family", "small", "any"],
    been: ["first", "some", "often", "any"],
    pace: ["calm", "balanced", "active", "any"],
    childage: ["tiny", "preschool", "school", "teen", "any"],
    walking: ["short", "stepfree", "long", "any"],
    distance: ["local", "adjacent", "wide", "any"],
    rain: ["backup", "indoor", "outdoors", "any"],
    exclude: ["thermal", "culture", "cable", "any"],
  };
  function shareCode(key) {
    const v = state.answers[key];
    return SHARE_VALUES[key].includes(v) ? v : "any";
  }
  function planHash() {
    const interests = state.interests.filter((t) => LABELS[t]);
    const main = SHARE_ORDER.map(shareCode).concat([
      interests.length ? interests.join(",") : "any",
      state.days >= 1 && state.days <= 7 ? String(state.days) : "0",
    ]);
    const refine = REFINE_KEYS.map(shareCode);
    if (refine.some((v) => v !== "any")) main.push.apply(main, refine);
    return "plan=" + main.join(".");
  }
  function shareUrl() {
    const url = new URL("/podbor", window.location.origin);
    url.hash = planHash();
    return url.toString();
  }
  function readSharedPlan() {
    const raw = String(window.location.hash || "").replace(/^#/, "");
    if (!raw.startsWith("plan=")) return null;
    const parts = raw.slice(5).split(".");
    if (parts.length !== 8 && parts.length !== 13) return null;
    const answers = {};
    for (let i = 0; i < SHARE_ORDER.length; i++) {
      if (!SHARE_VALUES[SHARE_ORDER[i]].includes(parts[i])) return null;
      answers[SHARE_ORDER[i]] = parts[i];
    }
    let interests = [];
    if (parts[6] !== "any") {
      interests = parts[6].split(",").filter(Boolean);
      if (!interests.length || interests.some((t) => !LABELS[t])) return null;
      answers.interests = interests.join(",");
    } else answers.interests = "any";
    if (!/^[0-7]$/.test(parts[7])) return null;
    if (parts.length === 13) {
      for (let i = 0; i < REFINE_KEYS.length; i++) {
        const v = parts[8 + i];
        if (!SHARE_VALUES[REFINE_KEYS[i]].includes(v)) return null;
        answers[REFINE_KEYS[i]] = v;
      }
    }
    return { answers: answers, interests: interests, days: parts[7] === "0" ? null : Number(parts[7]) };
  }
  function applySharedPlan(parsed) {
    state.answers = parsed.answers;
    state.interests = parsed.interests.slice();
    state.days = parsed.days;
    state.final = true;
    state.step = MAIN_N - 1;
    if (REFINE_KEYS.some((k) => state.answers[k] && state.answers[k] !== "any")) {
      refining = true;
      QUESTIONS.splice(MAIN_N, QUESTIONS.length - MAIN_N, ...REFINE_QUESTIONS.filter((q) => !q.children_only || childrenTrip()));
      state.step = QUESTIONS.length - 1;
    }
    started = true;
    goal("podbor_shared_open", {});
  }
  function copyShareLink(url) {
    const done = () => showToast("Ссылка скопирована");
    const fallback = () => {
      const ta = document.createElement("textarea");
      ta.value = url;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      ta.remove();
      if (ok) done();
      else showToast(url);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(fallback);
      return;
    }
    fallback();
  }
  function sharePlan() {
    const url = shareUrl();
    goal("podbor_share_click", {});
    const mobile = window.matchMedia("(max-width: 899px), (hover: none) and (pointer: coarse)").matches;
    if (mobile && typeof navigator.share === "function") {
      navigator.share({ title: "План поездки по Адыгее", url: url }).catch((err) => {
        if (err && err.name === "AbortError") return;
        copyShareLink(url);
      });
      return;
    }
    copyShareLink(url);
  }
  function captureCards() {
    const box = document.getElementById("results");
    return [...box.querySelectorAll(".podbor-card,.podbor-stop")].map((el, index) => ({
      key: el.dataset.type + el.dataset.id, rect: el.getBoundingClientRect(), index: index,
    }));
  }
  function animateCards(old) {
    if (!old || !old.length || reduced()) return;
    const now = [...document.querySelectorAll("#results .podbor-card,#results .podbor-stop")];
    now.forEach((el, index) => {
      const prev = old.find((x) => x.key === el.dataset.type + el.dataset.id);
      if (!prev) {
        el.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 450 });
        return;
      }
      const r = el.getBoundingClientRect();
      const dx = prev.rect.left - r.left;
      const dy = prev.rect.top - r.top;
      if (dx || dy) el.animate([{ transform: "translate(" + dx + "px," + dy + "px)" }, { transform: "none" }], { duration: 450 });
      if (prev.index > index) el.classList.add("moved-up");
    });
  }
  function renderResults() {
    const old = pendingCapture;
    pendingCapture = null;
    document.getElementById("results").innerHTML = state.final ? finalResults() : liveResults();
    if (old) animateCards(old);
  }
  function syncWizard() {
    root.classList.add("is-app");
    root.classList.toggle("is-flow", !state.final);
    root.classList.toggle("is-preview", !!(reviewOpen && !state.final));
    root.classList.toggle("is-plan", !!state.final);
    document.getElementById("wizard").classList.toggle("hidden", !!state.final);
    const layout = document.getElementById("podbor-layout");
    layout.classList.toggle("is-wide", !!state.final);
    layout.classList.toggle("is-preview", !!(reviewOpen && !state.final));
  }
  function render() {
    document.getElementById("wizard").innerHTML = wizard();
    syncWizard();
    renderResults();
    persist();
  }
  function updateAnswer(key, value, mutate) {
    const before = rankNow();
    const old = before.main.map((z) => keyOf(z.x)).join("|");
    pendingCapture = captureCards();
    lastKey = key;
    lastAnswer = value;
    phase += 1;
    mutate();
    const after = rankNow();
    const changed = old !== after.main.map((z) => keyOf(z.x)).join("|");
    lastUpdate = before.main.length !== after.main.length
      ? "Подобрано " + before.main.length + " → " + after.main.length
      : changed ? (value === "any" ? "Те же варианты · обновлён порядок для разнообразия" : "Перестроил порядок по ответу")
      : "Пожелание учтено · " + after.main.length + " вариантов";
    render();
  }
  function fireQ7(skipped) {
    markStart();
    const interests = skipped ? "" : state.interests.join(",");
    goal("podbor_q7_done", { q: "interests", interests: interests, skipped: skipped ? 1 : 0 });
    logEvent("answer", { question_id: "interests", answer_code: skipped ? "any" : (interests || "any"), skipped: !!skipped });
  }
  function choose(key, value, skipped) {
    if (busy) return;
    if (key === "interests") {
      markStart();
      const code = value === "any" ? "any" : null;
      updateAnswer(key, value, () => {
        if (value === "any") state.interests = [];
        else {
          const i = state.interests.indexOf(value);
          if (i < 0) state.interests.push(value); else state.interests.splice(i, 1);
        }
        state.answers.interests = state.interests.length ? state.interests.join(",") : "any";
      });
      if (code) logEvent("answer", { question_id: "interests", answer_code: "any", skipped: false });
      else logEvent("answer", { question_id: "interests", answer_code: state.interests.join(",") || "any", skipped: false });
      // Переключение тем на шаге остаётся мгновенным: реакция/лоадер только
      // при уходе со шага («Удивите меня», «Готово» / «Дальше», «Пропустить»).
      if (value === "any") {
        animateAnswer(key, value, () => finish({ immediate: true, fromAny: true }));
      }
      return;
    }
    markStart();
    if (Q_GOAL[key]) goal(Q_GOAL[key], { q: key, answer: value, skipped: skipped ? 1 : 0 });
    logEvent("answer", { question_id: key, answer_code: value, skipped: !!skipped });
    updateAnswer(key, value, () => {
      state.answers[key] = value;
      if (key === "party" && refining) {
        QUESTIONS.splice(MAIN_N, QUESTIONS.length - MAIN_N, ...REFINE_QUESTIONS.filter((q) => !q.children_only || childrenTrip()));
        if (!childrenTrip()) delete state.answers.childage;
      }
      state.limit = 6;
      state.days = null;
    });
    animateAnswer(key, value, () => {
      if (returnToReview) { showReview(); return; }
      if (refining && state.step >= QUESTIONS.length - 1) { showReview(); return; }
      state.step = refining ? state.step + 1 : Math.min(MAIN_N - 1, state.step + 1);
      render();
      scrollWizard();
    });
  }
  function skip() {
    const q = QUESTIONS[state.step];
    if (!q || busy) return;
    if (q.key === "interests") {
      updateAnswer("interests", "any", () => { state.interests = []; state.answers.interests = "any"; });
      finish({ skipped: true });
      return;
    }
    choose(q.key, "any", true);
  }
  function back() {
    if (busy) return;
    if (state.final) { state.final = false; state.step = Math.min(state.step, QUESTIONS.length - 1); }
    else state.step = Math.max(0, state.step - 1);
    render();
    scrollWizard();
  }
  function edit(i) {
    if (busy || !QUESTIONS[i]) return;
    goal("podbor_edit", { q: QUESTIONS[i].key });
    if (reviewOpen) returnToReview = true;
    reviewOpen = false;
    state.final = false;
    state.step = i;
    render();
    scrollWizard();
  }
  function closeReview() {
    reviewOpen = false;
    detailsOpen = false;
    const sheet = document.getElementById("review-sheet");
    if (sheet) sheet.classList.add("hidden");
    render();
  }
  function showReview() {
    if (busy) return;
    returnToReview = false;
    reviewOpen = true;
    goal("podbor_summary", {});
    const sheet = document.getElementById("review-sheet");
    if (sheet) sheet.classList.add("hidden");
    render();
    const wiz = document.getElementById("wizard");
    if (wiz) wiz.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
  }
  function finish(opts) {
    opts = opts || {};
    if (busy && !opts.immediate) return;
    fireQ7(!!opts.skipped);
    if (opts.immediate) { showReview(); return; }
    animateAnswer("summary", "any", showReview);
  }
  function confirmPlan() {
    if (busy) return;
    reviewOpen = false;
    detailsOpen = false;
    returnToReview = false;
    const sheet = document.getElementById("review-sheet");
    if (sheet) sheet.classList.add("hidden");
    state.planId = C.contextId();
    const ranked = rankNow();
    const days = C.planDays(ranked, answers(), { days: state.days });
    const points = days.reduce((sum, d) => sum + ((d.stops && d.stops.length) || 0), 0);
    goal("podbor_plan_build", { days: days.length, points: points, mode: ranked.mode, algo: C.VERSION });
    logEvent("plan_build", { answer_code: ranked.mode, plan_id: state.planId });
    animateAnswer("final", "any", () => {
      state.final = true;
      state.tab = "all";
      render();
      if (window.innerWidth < 900) document.getElementById("results").scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
    });
  }
  function restart() {
    if (busy) return;
    refining = false;
    QUESTIONS.splice(MAIN_N);
    closeReview();
    returnToReview = false;
    phase = 0;
    lastKey = null;
    lastAnswer = null;
    lastUpdate = "";
    fewKey = "";
    state = fresh();
    render();
    scrollWizard();
  }
  function startRefine() {
    if (busy) return;
    goal("podbor_refine_start", {});
    refining = true;
    QUESTIONS.splice(MAIN_N, QUESTIONS.length - MAIN_N, ...REFINE_QUESTIONS.filter((q) => !q.children_only || childrenTrip()));
    state.final = false;
    state.step = MAIN_N;
    render();
    scrollWizard();
  }
  function mutateAndRender(fn) {
    pendingCapture = captureCards();
    fn();
    render();
  }

  document.addEventListener("error", (e) => {
    const img = e.target;
    if (!img || img.tagName !== "IMG" || !root.contains(img)) return;
    const fb = img.getAttribute("data-fallback");
    if (!fb || img.dataset.fbUsed === "1" || img.getAttribute("src") === fb) return;
    img.dataset.fbUsed = "1";
    img.setAttribute("src", fb);
  }, true);

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (!b || !root.contains(b)) return;
    const d = b.dataset;
    if (busy && d.act !== "open" && d.act !== "bot") return;
    switch (d.act) {
      case "choose": choose(d.q, d.answer, false); break;
      case "skip": skip(); break;
      case "back": back(); break;
      case "edit": edit(+d.i); break;
      case "finish": finish(); break;
      case "confirm": confirmPlan(); break;
      case "details": detailsOpen = !detailsOpen; render(); break;
      case "closereview": closeReview(); break;
      case "restart": restart(); break;
      case "tab": state.tab = d.t; state.limit = 6; renderResults(); break;
      case "more": state.limit += 6; renderResults(); break;
      case "days": state.days = +d.n; renderResults(); persist(); break;
      case "alt": state.showAlt = !state.showAlt; logEvent("alt_toggle", { answer_code: state.showAlt ? "on" : "off" }); renderResults(); break;
      case "vote": {
        const next = state.votes[d.k] === d.v ? null : d.v;
        state.votes[d.k] = next;
        if (next) {
          goal(next === "up" ? "podbor_like" : "podbor_dislike", { item: d.k });
          logEvent(next === "up" ? "podbor_like" : "podbor_dislike", { item_key: d.k });
        }
        renderResults();
        break;
      }
      case "seen":
        mutateAndRender(() => { if (!state.seen.includes(d.k)) state.seen.push(d.k); });
        goal("place_seen_before", { item: d.k });
        logEvent("place_seen_before", { item_key: d.k });
        { const found = DATA.find((x) => keyOf(x) === d.k); showToast("Убрали «" + ((found && found.name) || "") + "» — на его место встало новое 🌿"); }
        break;
      case "unseen": mutateAndRender(() => { state.seen = []; }); break;
      case "pv":
        if (state.planVote !== d.v) {
          state.planVote = d.v;
          if (d.v === "up") goal("podbor_plan_like", {});
          else goal("podbor_plan_dislike", { reasons: state.planReasons.join(",") });
          logEvent("plan_vote", { answer_code: d.v });
        }
        renderResults();
        document.getElementById("feedback") && document.getElementById("feedback").scrollIntoView({ block: "nearest" });
        break;
      case "reason": {
        const i = state.planReasons.indexOf(d.r);
        if (i < 0) state.planReasons.push(d.r); else state.planReasons.splice(i, 1);
        logEvent("plan_dislike_reason", { answer_code: d.r });
        renderResults();
        document.getElementById("feedback") && document.getElementById("feedback").scrollIntoView({ block: "nearest" });
        break;
      }
      case "density":
        state.planDensity = d.d;
        logEvent("plan_density", { answer_code: d.d });
        renderResults();
        break;
      case "fix":
        logEvent("plan_fix", { answer_code: d.f });
        mutateAndRender(() => {
          if (d.f === "calm") state.answers.pace = "calm";
          if (d.f === "local") state.answers.distance = "local";
          if (d.f === "often") state.answers.been = "often";
          state.planReasons = [];
          state.planVote = null;
          phase += 1;
        });
        showToast("Пересобрал план ✅");
        break;
      case "bot":
        goal("podbor_feedback_max", { plan_id: planCode() });
        logEvent("podbor_feedback_max", { plan_id: planCode() }, true);
        break;
      case "open":
        goal("podbor_card_open", { item: d.item, position: Number(d.pos) || 0, block: d.block || "main" });
        break;
      case "refine": startRefine(); break;
      case "share": sharePlan(); break;
      case "club": goal("podbor_club_click", {}); break;
      case "toc": {
        const el = document.getElementById(d.target);
        if (el) { e.preventDefault(); el.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" }); }
        break;
      }
      case "yamaps": goal("podbor_yamaps_click", { day: Number(d.day) || 0 }); break;
      case "enough": showToast("Хорошо, план остаётся здесь. Можно вернуться к любому ответу 🌿"); break;
      default: break;
    }
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && reviewOpen) {
      if (detailsOpen) { detailsOpen = false; render(); return; }
      closeReview();
      return;
    }
    if (e.key === "Escape" && busy) {
      clearTimeout(timer);
      stopPhotoReel();
      document.getElementById("podbor-reaction").classList.remove("show");
      busy = false;
      render();
    }
  });
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });

  preloadPlacePhotos();
  const sharedPlan = readSharedPlan();
  if (sharedPlan) applySharedPlan(sharedPlan);
  else if (!boot.fresh) restore();
  let preset = "";
  if (boot.fresh && ["winter", "summer", "any"].includes(boot.season) && !state.answers.season) {
    state.answers.season = boot.season;
    state.step = 1;
    preset = boot.season;
  }
  render();
  if (preset) {
    markStart();
    goal("podbor_q1_done", { q: "season", answer: preset, skipped: 0 });
    logEvent("answer", { question_id: "season", answer_code: preset, skipped: false });
    holdReaction(reaction("season", preset));
  }
})();
