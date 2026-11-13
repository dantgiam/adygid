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
  function wizard() {
    const q = QUESTIONS[state.step] || QUESTIONS[0];
    if (state.final) {
      return '<div class="podbor-kicker">Ваши пожелания</div><h2>Поездка обретает форму</h2><div class="podbor-chips">' + summary() + '</div><button type="button" class="podbor-btn podbor-btn-ghost" data-act="back">← Изменить ответы</button><button type="button" class="podbor-skip" data-act="restart">Подобрать заново</button>';
    }
    const inRefine = refining && state.step >= MAIN_N;
    const list = inRefine ? QUESTIONS.slice(MAIN_N) : QUESTIONS.slice(0, MAIN_N);
    const pos = inRefine ? state.step - MAIN_N : state.step;
    const choices = q.options.map((o) => {
      const sel = q.key === "interests"
        ? (o[0] === "any" ? state.interests.length === 0 && state.answers.interests !== undefined : state.interests.includes(o[0]))
        : state.answers[q.key] === o[0];
      const exp = q.key === "pace" ? paceExplain(o[0]) : o[2];
      return '<button type="button" data-act="choose" data-q="' + q.key + '" data-answer="' + o[0] + '" class="podbor-choice' + (o[0] === "any" ? " is-any" : "") + (sel ? " is-on" : "") + '" aria-pressed="' + sel + '">' + (o[3] ? '<span class="podbor-choice-icon" aria-hidden="true">' + esc(o[3]) + "</span>" : "") + "<span><b>" + esc(o[1]) + "</b>" + (exp ? "<small>" + esc(exp) + "</small>" : "") + "</span></button>";
    }).join("");
    const finishBtn = q.key === "interests" ? '<button type="button" class="podbor-btn" data-act="finish">Проверить пожелания →</button>' : "";
    return '<div class="podbor-step"><span>' + (inRefine ? "Уточнение " + (pos + 1) + " из " + list.length : "Вопрос " + (pos + 1) + " из " + MAIN_N) + '</span><div class="podbor-dots">' + list.map((_, i) => '<i class="' + (i <= pos ? "is-on" : "") + '"></i>').join("") + '</div></div><div class="podbor-qicon" aria-hidden="true">' + esc(q.icon || "✦") + "</div><h2>" + esc(q.title || q.copy) + '</h2><p class="podbor-why-q">' + esc(q.why || "") + '</p><div class="podbor-choices">' + choices + "</div>" + finishBtn + '<div class="podbor-nav"><button type="button" class="podbor-btn podbor-btn-ghost" data-act="back"' + (state.step === 0 ? " disabled" : "") + '>← Назад</button><button type="button" class="podbor-skip" data-act="skip">' + (q.key === "interests" ? "Пропустить и посмотреть" : "Пропустить вопрос") + "</button></div>";
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
  function stopRow(z, i) {
    const x = z.x;
    const photo = x.image ? '<img src="' + esc(x.image) + '" alt="" loading="lazy">' : "";
    const drive = z.drive == null ? "" : '<div class="podbor-drive">🚗 ' + (i === 0 ? "от базы " : "") + "<b>≈ " + esc(C.fmtMin(z.drive)) + "</b> · оценка по координатам</div>";
    const winter = state.answers.season === "winter" && x.winter_ok === "unknown" ? " · <b>зимой уточнить подход</b>" : "";
    const also = z.kind === "also" ? ' · <span class="podbor-alsotag">не из ваших тем — по пути</span>' : "";
    return drive + '<div class="podbor-stop' + (z.kind === "also" ? " is-also" : "") + '" data-type="' + x.type + '" data-id="' + x.id + '"><div class="podbor-stop-photo">' + photo + '</div><div><h4>' + esc(x.name) + '</h4><div class="podbor-stop-meta">' + vt(x) + " · " + (x.type === "route" ? "маршрут" : "место") + also + winter + '</div><div class="podbor-why">' + esc(why(x)) + "</div>" + acts(x) + " " + moreLink(x, "plan", i) + "</div></div>";
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
    return '<section class="podbor-day"><div class="podbor-dayhead"><span>День ' + (i + 1) + "</span><div><h3>" + esc(AREA_NAMES[d.area] || "Адыгея") + '</h3><p>' + d.stops.length + " " + word + " · ≈ " + esc(C.fmtMin(d.totalMin)) + " с дорогой из ≈ " + esc(C.fmtMin(d.budget)) + ' на день</p></div></div>' + mapBtn + '<div class="podbor-bud" aria-hidden="true"><i class="is-visit" style="width:' + Math.min(100, vp) + '%"></i><i class="is-drive" style="width:' + Math.min(100 - Math.min(100, vp), dp) + '%"></i></div><p class="podbor-bud-label">зелёное — на местах, серое — дорога, пусто — запас (≥ 15%). Светлое время ≈ ' + esc(C.fmtMin(d.daylight)) + "." + (d.estimated ? " Есть оценочные длительности (≈)." : "") + '</p><div class="podbor-timeline">' + d.stops.map(stopRow).join("") + (d.returnDrive != null ? '<div class="podbor-drive">🚗 обратно на базу <b>≈ ' + esc(C.fmtMin(d.returnDrive)) + "</b></div>" : "") + "</div>" + (d.long ? '<p class="podbor-daynote">Длинный выход — на весь день, другие точки не добавляем.</p>' : "") + "</section>";
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
    if (state.planReasons.includes("been")) fix += '<div class="podbor-fix">Отметьте «✓ Уже был тут» на карточках — заменим их. Или <button type="button" class="podbor-btn podbor-btn-ghost" data-act="fix" data-f="often">покажите необычное</button></div>';
    const down = state.planVote === "down"
      ? '<div class="podbor-q">Что не так? Можно несколько</div><div class="podbor-row">' + reasons.map(([k, t]) => '<button type="button" data-act="reason" data-r="' + k + '" class="' + (state.planReasons.includes(k) ? "on" : "") + '">' + t + "</button>").join("") + "</div>" + fix
      : "";
    const density = state.planVote
      ? '<div class="podbor-q">Насколько насыщенные дни?</div><div class="podbor-row">' + [["low", "Можно больше"], ["ok", "В самый раз"], ["high", "Слишком много"]].map(([k, t]) => '<button type="button" data-act="density" data-d="' + k + '" class="' + (state.planDensity === k ? "on" : "") + '">' + t + "</button>").join("") + "</div>"
      : "";
    const href = "https://max.ru/se15002131_bot?start=podbor_" + planCode();
    return '<div class="podbor-feedback" id="feedback"><h3>Подошёл маршрут?</h3><div class="podbor-row"><button type="button" data-act="pv" data-v="up" class="' + (state.planVote === "up" ? "on" : "") + '">👍 Да</button><button type="button" data-act="pv" data-v="down" class="' + (state.planVote === "down" ? "on" : "") + '">👎 Не совсем</button></div>' + down + density + '<p class="podbor-q">Не нравится конкретное место — нажмите на карточке 👎 или «✓ Уже был тут».</p><a class="podbor-max" href="' + href + '" target="_blank" rel="noopener" data-act="bot">Дать обратную связь</a></div>';
  }
  function finalResults() {
    const R = rankNow();
    noteFew(R);
    const days = C.planDays(R, answers(), { days: state.days });
    const dur = state.answers.duration;
    const opts = dur === "short" ? [2, 3] : dur === "long" ? [4, 5, 6, 7] : [1];
    const dayBtns = opts.length > 1 ? '<div class="podbor-daycount">Сколько дней показать? ' + opts.map((n) => '<button type="button" class="podbor-tab' + (C.daysFor(answers(), state.days) === n ? " is-on" : "") + '" data-act="days" data-n="' + n + '">' + n + "</button>").join("") + "</div>" : "";
    return '<div class="podbor-kicker">Ваш план</div><h2 class="podbor-final-title">Адыгея, которая вам ближе</h2><button type="button" class="podbor-share" data-act="share">Поделиться / сохранить план ссылкой</button><div class="podbor-chips">' + summary() + "</div>" + modeNotice(R) + hiddenBar() + '<div class="podbor-notice"><b>План по времени, но не навигатор.</b> Время на месте — из данных сайта, а где их нет — оценка по типу места (≈). Дорога — оценка по координатам с поправкой на горные дороги. Часы работы, подходы и погоду на дату нужно проверить.' + (!C.baseAnchor(state.answers.base) ? " База не выбрана — дорогу от жилья не считаем." : "") + "</div>" + dayBtns + days.map(dayHtml).join("") + altBlock(R) + feedback() + '<div class="podbor-again"><h3>Хотите подстроить ещё точнее?</h3><p>Возраст детей, ходьба, непогода, что исключить. Всё необязательно.</p><div class="podbor-nav"><button type="button" class="podbor-btn" data-act="refine">Сделать точнее — ещё пара вопросов</button><button type="button" class="podbor-btn podbor-btn-ghost" data-act="enough">Достаточно</button></div></div><p class="podbor-fine">Ничего не забронировано. Подборка не обещает безопасность или выполнимость. Стоимость: уточняем, скоро появится :)</p>';
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
    document.getElementById("wizard").classList.toggle("hidden", reviewOpen || state.final);
    document.getElementById("podbor-layout").classList.toggle("is-wide", reviewOpen || state.final);
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
      animateAnswer(key, value, () => { if (value === "any") finish({ immediate: true, fromAny: true }); else render(); });
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
    if (reviewOpen) { closeReview(); returnToReview = true; }
    state.final = false;
    state.step = i;
    render();
    scrollWizard();
  }
  function closeReview() {
    reviewOpen = false;
    syncWizard();
    document.getElementById("review-sheet").classList.add("hidden");
  }
  function showReview() {
    if (busy) return;
    returnToReview = false;
    reviewOpen = true;
    goal("podbor_summary", {});
    syncWizard();
    document.getElementById("review-panel").innerHTML = '<div class="podbor-kicker">Остался один шаг</div><h2 id="review-title">' + esc(copyLine(COPY.summary, "Готово, все ваши пожелания собраны ✅")) + '</h2><p>Если нужно что-то поменять — нажмите на параметр. Если всё верно — формируем план.</p><button type="button" id="confirm-plan" class="podbor-btn" data-act="confirm">Сформировать план →</button><div class="podbor-kicker">Ваши параметры · нажмите, чтобы изменить</div>' + QUESTIONS.map((q, i) => '<button type="button" class="podbor-review-row" data-act="edit" data-i="' + i + '"><span><small>' + esc(q.copy) + "</small><b>" + esc(answerLabel(q)) + '</b></span><span>✎ изменить</span></button>').join("") + '<button type="button" class="podbor-skip" data-act="closereview">Вернуться к вопросам</button>';
    document.getElementById("review-sheet").classList.remove("hidden");
    renderResults();
    document.getElementById("results").scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
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
    closeReview();
    returnToReview = false;
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
      case "yamaps": goal("podbor_yamaps_click", { day: Number(d.day) || 0 }); break;
      case "enough": showToast("Хорошо, план остаётся здесь. Можно вернуться к любому ответу 🌿"); break;
      default: break;
    }
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && reviewOpen) { closeReview(); return; }
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
