/* Цели Яндекс.Метрики: санитизация параметров и список идентификаторов.
   Браузер: window.AdygidMetrica. Node: module.exports.
   В параметры не попадают свободный текст, контакты, запросы, сырые URL,
   токены и id сохранённого плана. Неизвестный идентификатор цели не уходит. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AdygidMetrica = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var COUNTER_ID = "111028002";
  var GOAL_LIMIT = 200;
  var ACCOUNT_GOALS_BEFORE = 82;

  /* Уже есть в счётчике и по-прежнему шлются кодом. */
  var EXISTING = [
    "random_place_refresh", "filter_apply", "favorite_toggle", "like_click",
    "read_25", "read_50", "read_75", "read_100", "scroll_75",
    "magnet_view", "magnet_click", "magnet_click_max", "magnet_click_tg",
    "podbor_cta_click", "weather_click", "external_map_click",
    "club_page_messenger_click", "place_card_click", "route_card_click",
    "club_cta_click", "club_nav_click", "faq_open", "toc_click", "page_read",
    "podbor_start", "podbor_result_few",
    "podbor_q1_done", "podbor_q2_done", "podbor_q3_done", "podbor_q4_done",
    "podbor_q5_done", "podbor_q6_done", "podbor_q7_done",
    "podbor_edit", "podbor_summary", "podbor_plan_build", "podbor_refine_start",
    "podbor_like", "podbor_dislike", "place_seen_before",
    "podbor_plan_like", "podbor_plan_dislike", "podbor_feedback_max", "podbor_card_open"
  ];

  /* Уже шлёт код, в счётчике этих id ещё нет (19 штук). Историю bot_max_click не трогаем. */
  var MISSING_IN_ACCOUNT = [
    "podbor_edit_click", "podbor_save_click", "club_click", "phone_click", "email_click",
    "bot_click_max", "bot_click_tg", "article_internal_link", "outbound_click", "review_click",
    "podbor_share_click", "podbor_shared_open", "podbor_yamaps_click", "podbor_club_click",
    "seasonal_click", "plan_save_max", "plan_save_tg", "partner_form_submit", "partner_cta_click"
  ];

  /* Новые идентификаторы этой поставки. Параметры вместо цели на каждый элемент. */
  var ADDED = [
    "menu_toggle", "nav_click", "filter_reset", "content_card_click", "accordion_open",
    "gallery_nav", "difficulty_open", "podbor_nav", "podbor_plan_adjust", "podbor_share_result",
    "podbor_save_attempt", "podbor_save_error", "podbor_error", "podbor_answer",
    "partner_form_invalid", "partner_form_error", "cookie_choice", "cookie_settings"
  ];

  var GOALS = {};
  EXISTING.concat(MISSING_IN_ACCOUNT, ADDED).forEach(function (id) { GOALS[id] = 1; });

  var QUESTIONS = {
    season: 1, duration: 1, base: 1, party: 1, been: 1, pace: 1, interests: 1,
    childage: 1, walking: 1, distance: 1, rain: 1, exclude: 1
  };
  var INTERESTS = { views: 1, water: 1, caves: 1, culture: 1, thermal: 1, familyfun: 1 };
  var REASONS = { far: 1, dense: 1, interests: 1, been: 1, other: 1 };
  var PLACEMENTS = {
    magnet: 1, review: 1, podbor: 1, club_page: 1, club_cta: 1, nav: 1,
    article: 1, page: 1, partners_done: 1
  };

  function oneOf(list) {
    var set = {};
    for (var i = 0; i < list.length; i++) set[list[i]] = 1;
    return function (v) {
      v = String(v == null ? "" : v);
      return set[v] ? v : null;
    };
  }

  function code(v) {
    v = String(v == null ? "" : v);
    if (!/^[a-z0-9_]{1,32}$/.test(v)) return null;
    if (/\d{7,}/.test(v)) return null;
    return v;
  }

  function idNum(v) {
    v = String(v == null ? "" : v);
    return /^\d{1,6}$/.test(v) ? v : null;
  }

  function intBetween(min, max) {
    return function (v) {
      if (typeof v === "boolean") return null;
      var n = typeof v === "number" ? v : (typeof v === "string" && /^-?\d+$/.test(v) ? Number(v) : NaN);
      if (!isFinite(n) || Math.floor(n) !== n || n < min || n > max) return null;
      return n;
    };
  }

  function item(v) {
    v = String(v || "");
    return /^(place|route):\d{1,6}$/.test(v) ? v : null;
  }

  function host(v) {
    v = String(v || "").toLowerCase().replace(/^www\./, "");
    if (!/^[a-z0-9.-]{1,80}$/.test(v) || v.indexOf("..") >= 0) return null;
    if (v.charAt(0) === "." || v.charAt(v.length - 1) === "." || v.indexOf(".") < 0) return null;
    return v;
  }

  function algo(v) {
    v = String(v || "");
    if (!v || v.length > 48) return null;
    if (/[@/?#]|https?:|www\.|[а-яё]/i.test(v) || /\d{7,}/.test(v)) return null;
    if (!/^[\w. ·\-]+$/.test(v)) return null;
    return v;
  }

  function csv(dict) {
    return function (v) {
      if (v == null || v === "") return "";
      var parts = String(v).split(",");
      if (!parts.length) return null;
      for (var i = 0; i < parts.length; i++) if (!dict[parts[i]]) return null;
      return parts.join(",");
    };
  }

  function slug(v) {
    v = String(v || "");
    return /^[a-z0-9-]{1,80}$/.test(v) ? v : null;
  }

  var pageType = oneOf(["place", "route", "article", "scenario", "district", "page"]);
  var messenger = oneOf(["max", "tg", "telegram"]);
  var onOff = oneOf(["on", "off"]);
  var placement = function (v) { v = String(v || ""); return PLACEMENTS[v] ? v : null; };
  var qKey = function (v) { v = String(v || ""); return QUESTIONS[v] ? v : null; };
  var interests = csv(INTERESTS);
  var reasons = csv(REASONS);

  function pathOnly(value) {
    var s = String(value == null ? "" : value).trim();
    if (!s || s.charAt(0) === "#") return "";
    s = s.split("#")[0].split("?")[0];
    var abs = s.match(/^https?:\/\/[^/]+(\/.*)?$/i);
    if (abs) s = abs[1] || "/";
    else if (/^[a-z][a-z0-9+.-]*:/i.test(s)) return "";
    if (s.charAt(0) !== "/") return "";
    if (s.length > 1 && s.charAt(s.length - 1) === "/") s = s.slice(0, -1);
    return s;
  }

  function pathInfo(value) {
    var s = pathOnly(value);
    if (!s) return null;
    var rules = [
      [/^\/$/, function () { return { template: "/" }; }],
      [/^\/mesta\/(\d{1,6})$/, function (m) { return { template: "/mesta/{id}", item: "place:" + m[1] }; }],
      [/^\/mesta$/, function () { return { template: "/mesta" }; }],
      [/^\/marshruty\/(\d{1,6})\/track\.gpx$/, function (m) { return { template: "/marshruty/{id}/track.gpx", item: "route:" + m[1] }; }],
      [/^\/marshruty\/(\d{1,6})$/, function (m) { return { template: "/marshruty/{id}", item: "route:" + m[1] }; }],
      [/^\/marshruty$/, function () { return { template: "/marshruty" }; }],
      [/^\/stati\/([a-z0-9-]{1,80})$/, function (m) { return { template: "/stati/{slug}", slug: m[1] }; }],
      [/^\/stati$/, function () { return { template: "/stati" }; }],
      [/^\/kuda\/([a-z0-9-]{1,80})$/, function (m) { return { template: "/kuda/{slug}", slug: m[1] }; }],
      [/^\/kuda$/, function () { return { template: "/kuda" }; }],
      [/^\/okrugi\/([a-z0-9-]{1,40})$/, function (m) { return { template: "/okrugi/{slug}", slug: m[1] }; }],
      [/^\/okrugi$/, function () { return { template: "/okrugi" }; }],
      [/^\/podbor$/, function () { return { template: "/podbor" }; }],
      [/^\/klub$/, function () { return { template: "/klub" }; }],
      [/^\/voprosy$/, function () { return { template: "/voprosy" }; }],
      [/^\/partners$/, function () { return { template: "/partners" }; }],
      [/^\/privacy$/, function () { return { template: "/privacy" }; }],
      [/^\/soglasie$/, function () { return { template: "/soglasie" }; }],
      [/^\/naugad$/, function () { return { template: "/naugad" }; }]
    ];
    for (var i = 0; i < rules.length; i++) {
      var m = s.match(rules[i][0]);
      if (m) return rules[i][1](m);
    }
    if (/^\/(?:mesta\/\{id\}|marshruty\/\{id\}(?:\/track\.gpx)?|stati\/\{slug\}|kuda\/\{slug\}|okrugi\/\{slug\})$/.test(s)) {
      return { template: s };
    }
    if (s === "/" || /^\/(mesta|marshruty|stati|kuda|okrugi|podbor|klub|voprosy|partners|privacy|soglasie|naugad)$/.test(s)) {
      return { template: s };
    }
    return null;
  }

  function blocked(loc) {
    loc = loc || {};
    var hostName = String(loc.hostname || "").toLowerCase().replace(/\.$/, "");
    var path = pathOnly(loc.pathname || "/") || "/";
    if (path === "/admin" || path.indexOf("/admin/") === 0) return true;
    if (path === "/api" || path.indexOf("/api/") === 0) return true;
    if (path === "/login" || path.indexOf("/login/") === 0) return true;
    if (path === "/auth" || path.indexOf("/auth/") === 0) return true;
    if (path === "/bot" || path.indexOf("/bot/") === 0) return true;
    if (path.indexOf("/static/") === 0 || path.indexOf("/assets/") === 0) return true;
    var allowHost = false;
    try {
      var g = typeof window !== "undefined" ? window : root;
      allowHost = !!(g && g.ADYGID_METRICA_ALLOW_HOST === true);
    } catch (e) { allowHost = false; }
    if (!allowHost && (hostName === "localhost" || hostName === "127.0.0.1" || hostName === "0.0.0.0" || /\.local$/.test(hostName))) return true;
    return false;
  }

  var PATH_KEYS = { page: 1, list: 1, href: 1, target: 1 };
  var SCHEMAS = {
    review_click: { page_type: pageType, page_id: idNum, messenger: messenger },
    random_place_refresh: { item: item },
    filter_apply: { page: 1, field: oneOf(["type", "district", "paid", "kid", "difficulty"]), value: 1 },
    favorite_toggle: { item: item, state: onOff },
    like_click: { item: item, state: onOff },
    read_25: { page: 1, seconds: intBetween(0, 86400) },
    read_50: { page: 1, seconds: intBetween(0, 86400) },
    read_75: { page: 1, seconds: intBetween(0, 86400) },
    read_100: { page: 1, seconds: intBetween(0, 86400) },
    scroll_75: { page_type: oneOf(["article", "route", "place"]) },
    magnet_view: { magnet_id: idNum, page: 1, seconds: intBetween(0, 86400) },
    phone_click: { placement: placement },
    email_click: { placement: placement },
    bot_click_max: { placement: placement, host: host },
    bot_click_tg: { placement: placement, host: host },
    article_internal_link: { href: 1, page: 1, item: item, slug: slug },
    outbound_click: { host: host, placement: placement },
    magnet_click: { magnet_id: idNum, page: 1, messenger: messenger, seconds: intBetween(0, 86400), depth: intBetween(0, 100), section: slug },
    magnet_click_max: { magnet_id: idNum, page: 1, messenger: messenger, seconds: intBetween(0, 86400), depth: intBetween(0, 100), section: slug },
    magnet_click_tg: { magnet_id: idNum, page: 1, messenger: messenger, seconds: intBetween(0, 86400), depth: intBetween(0, 100), section: slug },
    podbor_cta_click: { src: code, season_chip: oneOf(["winter", "summer", "any"]) },
    seasonal_click: { target: 1 },
    weather_click: { item: item },
    external_map_click: { item: item },
    club_page_messenger_click: { messenger: oneOf(["max", "tg"]) },
    place_card_click: { item: item, list: 1 },
    route_card_click: { item: item, list: 1 },
    club_cta_click: { page: 1, seconds: intBetween(0, 86400), depth: intBetween(0, 100) },
    club_click: { placement: oneOf(["club_cta", "nav", "podbor"]), page: 1 },
    club_nav_click: { page: 1, seconds: intBetween(0, 86400) },
    faq_open: { page: 1, index: intBetween(1, 40) },
    toc_click: { page: 1 },
    page_read: { page: 1, seconds: intBetween(0, 86400), depth: intBetween(0, 100), section: slug },
    podbor_start: { src: code },
    podbor_result_few: { mode: oneOf(["all", "ok", "few", "none"]), interests: interests },
    podbor_save_click: {},
    plan_save_max: { days: intBetween(1, 7) },
    plan_save_tg: { days: intBetween(1, 7) },
    podbor_shared_open: { src: code },
    podbor_share_click: {},
    podbor_q1_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q2_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q3_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q4_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q5_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q6_done: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    podbor_q7_done: { q: qKey, interests: interests, skipped: intBetween(0, 1) },
    podbor_edit: { q: qKey },
    podbor_summary: {},
    podbor_plan_build: { days: intBetween(1, 7), points: intBetween(0, 84), mode: oneOf(["all", "ok", "few", "none"]), algo: algo },
    podbor_refine_start: {},
    podbor_edit_click: {},
    podbor_like: { item: item },
    podbor_dislike: { item: item },
    place_seen_before: { item: item },
    podbor_plan_like: {},
    podbor_plan_dislike: { reasons: reasons },
    podbor_feedback_max: {},
    podbor_card_open: { item: item, position: intBetween(0, 40), block: oneOf(["main", "preview", "plan", "also", "alt"]) },
    podbor_club_click: {},
    podbor_yamaps_click: { day: intBetween(1, 7) },
    partner_cta_click: { place: oneOf(["hero", "final", "sticky"]) },
    partner_form_submit: { category: code, subcategory: code },
    menu_toggle: { state: oneOf(["open", "close"]) },
    nav_click: { area: oneOf(["menu", "header", "hero", "see_all", "footer", "route_stop", "district"]), target: 1 },
    filter_reset: { page: 1 },
    content_card_click: { kind: oneOf(["article", "district", "more", "door", "mentioned", "showcase"]), target: 1 },
    accordion_open: { kind: oneOf(["toc", "partners"]), id: code },
    gallery_nav: { kind: oneOf(["carousel", "article"]), dir: oneOf(["prev", "next", "dot"]), index: intBetween(1, 40) },
    difficulty_open: { page: 1 },
    podbor_nav: { action: oneOf(["back", "restart", "more", "tab", "alt", "unseen", "toc", "enough", "notice_open", "notice_close"]), tab: oneOf(["all", "route", "place"]), state: onOff },
    podbor_plan_adjust: { action: oneOf(["reason", "density", "fix", "day"]), value: 1 },
    podbor_share_result: { result: oneOf(["copied", "shared", "failed"]) },
    podbor_save_attempt: { channel: oneOf(["max", "tg"]), retry: intBetween(0, 1) },
    podbor_save_error: { channel: oneOf(["max", "tg"]) },
    podbor_error: { code: oneOf(["empty", "boot"]) },
    podbor_answer: { q: qKey, answer: code, skipped: intBetween(0, 1) },
    partner_form_invalid: { field: oneOf(["company", "category", "location", "services", "discount", "contact", "consent"]) },
    partner_form_error: { code: oneOf(["http", "network"]) },
    cookie_choice: { choice: oneOf(["accepted"]) },
    cookie_settings: { action: oneOf(["open"]) }
  };

  function put(out, key, value) {
    if (value === null || value === undefined || value === "") return;
    out[key] = value;
  }

  function filterValue(field, value) {
    if (value == null || value === "") return "any";
    var v = String(value);
    if (field === "paid" || field === "kid") return v === "0" || v === "1" ? v : null;
    if (field === "difficulty") return /^(easy|medium|hard)$/.test(v) ? v : null;
    if (field === "type") return /^\d{1,6}$/.test(v) ? v : null;
    if (field === "district") return /^[a-z0-9-]{1,40}$/.test(v) ? v : null;
    return null;
  }

  function adjustValue(action, value) {
    var v = String(value == null ? "" : value);
    if (action === "day") return /^[1-7]$/.test(v) ? v : null;
    if (action === "reason") return REASONS[v] ? v : null;
    if (action === "density") return /^(low|ok|high)$/.test(v) ? v : null;
    if (action === "fix") return /^(calm|local|often)$/.test(v) ? v : null;
    return null;
  }

  function sanitize(name, params) {
    if (!GOALS[name] || name === "bot_max_click") return null;
    var schema = SCHEMAS[name];
    if (!schema) return null;
    var src = params && typeof params === "object" ? params : {};
    var out = {};
    var infoByKey = {};
    for (var key in schema) {
      if (!Object.prototype.hasOwnProperty.call(schema, key)) continue;
      if (PATH_KEYS[key]) {
        if (src[key] == null || src[key] === "") continue;
        var info = pathInfo(src[key]);
        if (!info) continue;
        infoByKey[key] = info;
        out[key] = info.template;
        continue;
      }
      if (key === "value") continue;
      if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
      var fn = schema[key];
      if (typeof fn !== "function") continue;
      put(out, key, fn(src[key]));
    }
    if (schema.item && !out.item) {
      var itemKeys = ["href", "target", "page", "list"];
      for (var ii = 0; ii < itemKeys.length && !out.item; ii++) {
        if (infoByKey[itemKeys[ii]] && infoByKey[itemKeys[ii]].item) out.item = infoByKey[itemKeys[ii]].item;
      }
    }
    if (schema.slug && !out.slug) {
      var slugKeys = ["href", "target", "page", "list"];
      for (var si = 0; si < slugKeys.length && !out.slug; si++) {
        if (infoByKey[slugKeys[si]] && infoByKey[slugKeys[si]].slug) out.slug = infoByKey[slugKeys[si]].slug;
      }
    }
    if (name === "filter_apply") {
      var fv = filterValue(out.field, src.value);
      if (out.field && fv) out.value = fv;
    }
    if (name === "podbor_plan_adjust") {
      var av = adjustValue(out.action, src.value);
      if (out.action && av) out.value = av;
    }
    return { name: name, params: out };
  }

  return {
    COUNTER_ID: COUNTER_ID,
    GOAL_LIMIT: GOAL_LIMIT,
    ACCOUNT_GOALS_BEFORE: ACCOUNT_GOALS_BEFORE,
    EXISTING: EXISTING.slice(),
    MISSING_IN_ACCOUNT: MISSING_IN_ACCOUNT.slice(),
    ADDED: ADDED.slice(),
    goals: function () { return Object.keys(GOALS); },
    has: function (name) { return !!GOALS[name]; },
    sanitize: sanitize,
    pathInfo: pathInfo,
    blocked: blocked
  };
});
