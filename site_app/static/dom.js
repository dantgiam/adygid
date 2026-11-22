/* Галерея первого экрана, FAQ, карточка услуги и демо-заявка.
   Заявка не отправляется: ни fetch, ни запись в базу. */
(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var slides = document.querySelectorAll(".dom-hero-img");
  var cap = document.querySelector("[data-dom-cap]");
  var count = document.querySelector("[data-dom-count]");
  var gal = document.getElementById("dom-gal");
  var index = 0;

  function show(next) {
    if (!slides.length) return;
    index = (next + slides.length) % slides.length;
    slides.forEach(function (img, n) { img.classList.toggle("is-on", n === index); });
    var current = slides[index];
    if (cap) cap.textContent = current.getAttribute("data-caption") || "";
    if (count) count.textContent = (index + 1) + " / " + slides.length;
  }
  var prev = document.querySelector("[data-dom-prev]");
  var next = document.querySelector("[data-dom-next]");
  if (prev) prev.addEventListener("click", function () { show(index - 1); });
  if (next) next.addEventListener("click", function () { show(index + 1); });
  if (gal) {
    gal.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") { event.preventDefault(); show(index + 1); }
      if (event.key === "ArrowLeft") { event.preventDefault(); show(index - 1); }
    });
  }

  document.querySelectorAll("[data-dom-dialog]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dlg = document.getElementById(button.getAttribute("data-dom-dialog") || "");
      if (dlg && dlg.showModal) dlg.showModal();
    });
  });
  document.querySelectorAll("dialog.dom-sheet").forEach(function (dlg) {
    if (dlg.id === "dom-sheet") return;
    var closeBtn = dlg.querySelector("[data-dom-close]");
    if (closeBtn) closeBtn.addEventListener("click", function () { dlg.close(); });
    dlg.addEventListener("click", function (event) {
      if (event.target === dlg) dlg.close();
    });
  });

  var tabs = [].slice.call(document.querySelectorAll("[data-dom-tab]"));
  var tabSections = tabs.map(function (tab) {
    return { tab: tab, el: document.getElementById((tab.getAttribute("href") || "").slice(1)) };
  }).filter(function (item) { return item.el; });
  function markTab() {
    if (!tabSections.length) return;
    var line = window.scrollY + 140;
    var current = tabSections[0];
    tabSections.forEach(function (item) {
      if (item.el.offsetTop <= line) current = item;
    });
    tabSections.forEach(function (item) {
      var on = item === current;
      item.tab.classList.toggle("is-on", on);
      if (on) item.tab.setAttribute("aria-current", "true");
      else item.tab.removeAttribute("aria-current");
    });
  }
  window.addEventListener("scroll", markTab, { passive: true });
  markTab();

  var faqAll = document.getElementById("faq-all");
  if (faqAll) {
    faqAll.addEventListener("click", function () {
      var open = faqAll.getAttribute("aria-pressed") !== "true";
      document.querySelectorAll("#faq details").forEach(function (item) { item.open = open; });
      faqAll.setAttribute("aria-pressed", open ? "true" : "false");
      faqAll.textContent = open ? "Свернуть все" : "Развернуть все";
    });
  }
  document.querySelectorAll('a[href^="#faq-"]').forEach(function (link) {
    link.addEventListener("click", function () {
      var id = link.getAttribute("href").slice(1);
      var node = document.getElementById(id);
      if (node && node.tagName === "DETAILS") node.open = true;
    });
  });

  document.querySelectorAll("[data-dom-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-dom-copy") || "";
      var status = document.getElementById(button.getAttribute("aria-describedby") || "");
      function report(ok) {
        if (status) status.textContent = ok ? "Пароль скопирован" : "Не вышло скопировать: выделите пароль вручную";
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { report(true); }, function () { report(false); });
        return;
      }
      report(false);
    });
  });

  document.querySelectorAll("img[data-fallback]").forEach(function (img) {
    img.addEventListener("error", function () {
      var next = img.getAttribute("data-fallback");
      if (!next || img.getAttribute("src") === next) return;
      img.removeAttribute("srcset");
      img.setAttribute("src", next);
    });
  });

  var raw = document.getElementById("dom-services");
  var services = raw ? JSON.parse(raw.textContent) : [];
  var byId = {};
  services.forEach(function (item) { byId[item.id] = item; });
  var sheet = document.getElementById("dom-sheet");
  var current = null;

  function step(name) {
    if (!sheet) return;
    sheet.querySelectorAll("[data-dom-step]").forEach(function (node) {
      node.hidden = node.getAttribute("data-dom-step") !== name;
    });
  }
  function fill(item) {
    current = item;
    var photo = sheet.querySelector("[data-dom-photo]");
    photo.replaceChildren();
    if (item.photo && item.photo.src) {
      var img = document.createElement("img");
      img.src = item.photo.src;
      img.alt = item.photo.alt || "";
      photo.appendChild(img);
      photo.hidden = false;
    } else {
      photo.hidden = true;
    }
    sheet.querySelector("[data-dom-title]").textContent = item.title;
    sheet.querySelector("[data-dom-price]").textContent = item.price + " " + item.unit;
    sheet.querySelector("[data-dom-about]").textContent = item.about;
    sheet.querySelector("[data-dom-duration]").textContent = item.duration;
    var list = sheet.querySelector("[data-dom-includes]");
    list.replaceChildren();
    (item.includes || []).forEach(function (line) {
      var li = document.createElement("li");
      var mark = document.createElement("span");
      mark.className = "dom-tick";
      mark.setAttribute("aria-hidden", "true");
      li.appendChild(mark);
      li.appendChild(document.createTextNode(line));
      list.appendChild(li);
    });
    step("detail");
  }
  document.querySelectorAll("[data-dom-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      var item = byId[button.getAttribute("data-dom-open")];
      if (!item || !sheet || !sheet.showModal) return;
      fill(item);
      sheet.showModal();
    });
  });
  if (sheet) {
    sheet.querySelector("[data-dom-close]").addEventListener("click", function () { sheet.close(); });
    sheet.querySelector("[data-dom-book]").addEventListener("click", function () { step("book"); });
    sheet.querySelector("[data-dom-preview]").addEventListener("click", function () {
      var date = sheet.querySelector("[data-dom-date]").value || "дату выберете сами";
      var time = sheet.querySelector("[data-dom-time]").value;
      var guests = sheet.querySelector("[data-dom-guests]").value || "2";
      var title = current ? current.title : "Услуга";
      sheet.querySelector("[data-dom-summary]").textContent =
        title + ", " + date + ", " + time + ", гостей: " + guests + ". Пример " + (current ? current.price : "") + ".";
      step("done");
    });
    sheet.addEventListener("click", function (event) {
      if (event.target === sheet) sheet.close();
    });
  }
  var sticky = document.querySelector(".dom-sticky");
  var hero = document.querySelector(".dom-hero");
  function placeSticky() {
    if (!sticky || !hero) return;
    var past = window.scrollY > hero.offsetHeight * 0.72;
    sticky.classList.toggle("is-on", past);
  }
  window.addEventListener("scroll", placeSticky, { passive: true });
  placeSticky();
  if (reduce) {
    document.documentElement.style.scrollBehavior = "auto";
    if (sticky) sticky.style.transition = "none";
  }
})();
