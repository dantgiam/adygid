/* Анкета партнёра на /partneram: подкатегории по направлению, отправка JSON,
   цель Метрики partner_form_submit (через adygidGoal — только после согласия на cookie). */
(function () {
  var form = document.getElementById("partner-form");
  if (!form) return;
  var tax = [];
  try { tax = JSON.parse(form.getAttribute("data-taxonomy") || "[]"); } catch (e) {}
  var cat = form.querySelector("#pf-cat"), sub = form.querySelector("#pf-sub");
  var err = document.getElementById("pf-error"), btn = document.getElementById("pf-submit");
  var goal = function (n, p) { if (typeof window.adygidGoal === "function") window.adygidGoal(n, p || {}); };

  cat.addEventListener("change", function () {
    var c = tax.filter(function (x) { return x.code === cat.value; })[0];
    sub.innerHTML = "";
    var o = document.createElement("option");
    o.value = ""; o.textContent = c ? "Выберите (необязательно)" : "Сначала направление";
    sub.appendChild(o);
    (c ? c.subs : []).forEach(function (s) {
      var op = document.createElement("option"); op.value = s.code; op.textContent = s.title; sub.appendChild(op);
    });
    sub.disabled = !c;
  });

  document.querySelectorAll('[data-goal="partner_cta_click"]').forEach(function (a) {
    a.addEventListener("click", function () { goal("partner_cta_click", { place: "hero" }); });
  });

  function val(name) { var el = form.elements[name]; return el ? (el.value || "").trim() : ""; }
  function list(name) {
    return Array.prototype.slice.call(form.querySelectorAll('input[name="' + name + '"]:checked')).map(function (i) { return i.value; });
  }
  function fail(msg, field) {
    err.textContent = msg; err.hidden = false;
    if (field && form.elements[field]) form.elements[field].focus();
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    err.hidden = true;
    if (val("company").length < 2) return fail("Укажите название или имя.", "company");
    if (!val("category")) return fail("Выберите направление.", "category");
    if (val("location").length < 2) return fail("Напишите, где вы работаете.", "location");
    if (val("services").length < 3) return fail("Коротко опишите услуги.", "services");
    if (!val("discount")) return fail("Укажите скидку клиентам АдыГида: это ваша цена за клиента.", "discount");
    if (form.elements.contact_phone && !val("contact_phone") && !val("contact_messenger")) return fail("Оставьте телефон или мессенджер.", "contact_phone");
    if (!form.elements.consent.checked) return fail("Нужно согласие на обработку данных.", "consent");
    var body = {
      company: val("company"), category: val("category"), subcategory: val("subcategory") || null,
      location: val("location"), services: val("services"), prices: val("prices") || null,
      seasons: list("seasons"), discount: val("discount"), booking_terms: val("booking_terms") || null,
      website: val("website") || null, socials: val("socials") || null, lead_channels: list("lead_channels"),
      comment: val("comment") || null, consent: true, source: "partneram", website_hp: val("website_hp") || null
    };
    ["contact_name", "contact_phone", "contact_messenger"].forEach(function (k) { if (form.elements[k]) body[k] = val(k) || null; });
    btn.disabled = true; btn.textContent = "Отправляем…";
    fetch("/api/partners/apply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) {
          var d = res.d && res.d.detail;
          throw new Error(typeof d === "string" ? d : "Проверьте поля анкеты.");
        }
        goal("partner_form_submit", { category: body.category, subcategory: body.subcategory || "" });
        document.getElementById("pd-code").textContent = res.d.code;
        document.getElementById("pd-max").href = res.d.bot.max;
        document.getElementById("pd-tg").href = res.d.bot.telegram;
        if (!res.d.contacts_via_bot) {
          document.getElementById("pd-text").textContent = "Мы свяжемся с вами в ближайшие дни. Если удобнее, напишите нам в бот: по коду из ссылки мы поймём, что это вы.";
        }
        form.hidden = true;
        var done = document.getElementById("partner-done");
        done.hidden = false;
        done.scrollIntoView({ behavior: "smooth", block: "center" });
      })
      .catch(function (e) { fail(e.message || "Не получилось отправить. Попробуйте ещё раз."); })
      .then(function () { btn.disabled = false; btn.textContent = "Отправить анкету"; });
  });
})();
