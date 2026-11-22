/* Галерея, фильтр категорий и копирование пароля-заглушки. Без библиотек. */
(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var track = document.querySelector("[data-dom-gal]");
  if (track) {
    var slides = track.children;
    var statusDots = document.querySelectorAll("[data-dom-dot]");
    function index() {
      var width = track.clientWidth || 1;
      var i = Math.round(track.scrollLeft / width);
      if (i < 0) return 0;
      if (i > slides.length - 1) return slides.length - 1;
      return i;
    }
    function go(next) {
      var count = slides.length;
      var i = (next + count) % count;
      track.scrollTo({ left: i * track.clientWidth, behavior: reduce ? "auto" : "smooth" });
    }
    function paint() {
      var i = index();
      statusDots.forEach(function (dot, n) {
        if (n === i) dot.setAttribute("aria-current", "true");
        else dot.removeAttribute("aria-current");
      });
    }
    var prev = document.querySelector("[data-dom-prev]");
    var next = document.querySelector("[data-dom-next]");
    if (prev) prev.addEventListener("click", function () { go(index() - 1); });
    if (next) next.addEventListener("click", function () { go(index() + 1); });
    statusDots.forEach(function (dot, n) {
      dot.addEventListener("click", function () { go(n); });
    });
    track.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") { event.preventDefault(); go(index() + 1); }
      if (event.key === "ArrowLeft") { event.preventDefault(); go(index() - 1); }
    });
    var ticking = false;
    track.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () { paint(); ticking = false; });
    }, { passive: true });
    paint();
  }

  var filters = document.querySelectorAll("[data-dom-filter]");
  var live = document.querySelector("[data-dom-filter-live]");
  function applyFilter(name) {
    var shown = 0;
    document.querySelectorAll("[data-dom-place]").forEach(function (card) {
      var ok = name === "all" || card.getAttribute("data-dom-cat") === name;
      card.hidden = !ok;
      if (ok) shown += 1;
    });
    filters.forEach(function (button) {
      var on = button.getAttribute("data-dom-filter") === name;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (live) live.textContent = "Показано мест: " + shown;
  }
  filters.forEach(function (button) {
    button.addEventListener("click", function () {
      applyFilter(button.getAttribute("data-dom-filter"));
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
      var area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (error) { ok = false; }
      area.remove();
      report(ok);
    });
  });
})();
