// Случайное место/маршрут — колода карточек поверх серверного рендера.
(function () {
  const card = document.getElementById("highlight-card");
  const btn = document.getElementById("regenerate-btn");
  if (!btn || !card) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let nextItem = null;      // следующая карточка, взятая заранее
  let busy = false;

  // Тянем следующую заранее, чтобы клик срабатывал мгновенно, а не ждал сеть.
  async function prefetch() {
    try {
      const res = await fetch("/api/site/random");
      if (res.ok) nextItem = await res.json();
    } catch (e) {
      nextItem = null;
    }
  }

  function paint(data) {
    if (!data) return;
    card.querySelector(".hl-tag").textContent = data.tag_label;
    card.querySelector(".hl-cover").style.backgroundImage = data.cover ? `url('${data.cover}')` : "";
    card.querySelector("h3").textContent = data.name;
    card.querySelector("p").textContent = data.excerpt || "";
    card.querySelector(".hl-open").href = data.url;
  }

  async function deal(direction) {
    if (busy) return;
    busy = true;
    card.classList.remove("nudge");

    // Если предзагрузка не успела — ждём её здесь, но это редкий случай.
    if (!nextItem) await prefetch();
    const data = nextItem;
    nextItem = null;
    prefetch();

    if (!data) { busy = false; return; }

    if (reduceMotion) {
      paint(data);
      busy = false;
      return;
    }

    card.style.setProperty("--dir", direction >= 0 ? 1 : -1);
    card.classList.add("tossing");
    card.addEventListener("animationend", function onToss() {
      card.removeEventListener("animationend", onToss);
      card.classList.remove("tossing");
      card.style.transform = "";
      paint(data);
      card.classList.add("dealing");
      card.addEventListener("animationend", function onDeal() {
        card.removeEventListener("animationend", onDeal);
        card.classList.remove("dealing");
        busy = false;
      }, { once: true });
    }, { once: true });
  }

  btn.addEventListener("click", () => deal(1));

  // ── Свайп/перетаскивание верхней карточки ──
  let startX = 0, startY = 0, dx = 0, dragging = false;
  const THRESHOLD = 90;

  card.addEventListener("pointerdown", (e) => {
    // Клики по кнопкам внутри карточки не должны превращаться в свайп
    if (busy || e.target.closest("a, button")) return;
    dragging = true; dx = 0;
    startX = e.clientX; startY = e.clientY;
    card.classList.add("dragging");
    card.setPointerCapture(e.pointerId);
  });

  card.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dx = e.clientX - startX;
    // Вертикальный жест — это скролл страницы, не наше дело
    if (Math.abs(e.clientY - startY) > Math.abs(dx) && Math.abs(dx) < 12) return;
    card.style.transform = `translateX(${dx}px) rotate(${dx / 22}deg)`;
    card.style.opacity = String(Math.max(0.45, 1 - Math.abs(dx) / 420));
  });

  function endDrag(e) {
    if (!dragging) return;
    dragging = false;
    card.classList.remove("dragging");
    try { card.releasePointerCapture(e.pointerId); } catch (err) { /* уже отпущен */ }

    if (Math.abs(dx) > THRESHOLD) {
      card.style.transform = "";
      card.style.opacity = "";
      deal(dx);
    } else {
      // Не дотянули — карточка мягко возвращается на место
      card.classList.add("settling");
      card.style.transform = "";
      card.style.opacity = "";
      setTimeout(() => card.classList.remove("settling"), 240);
    }
    dx = 0;
  }

  card.addEventListener("pointerup", endDrag);
  card.addEventListener("pointercancel", endDrag);

  // Однократный намёк, что карточку можно тянуть — только при первом визите
  try {
    if (!reduceMotion && !localStorage.getItem("adygid_deck_hinted")) {
      card.classList.add("nudge");
      localStorage.setItem("adygid_deck_hinted", "1");
    }
  } catch (e) { /* localStorage недоступен — просто без подсказки */ }

  prefetch();
})();

// ── Фоновые стикеры ──────────────────────────────────────────────────────
// Раскладываем скриптом, а не руками в шаблоне: только здесь известны реальная
// высота страницы и реальная ширина боковых полей, поэтому стикеры равномерно
// устилают всё свободное место — от края экрана до колонки текста и на всю
// длину ленты, а не сидят в паре заранее вбитых точек.
(() => {
  const layer = document.querySelector(".bg-stickers");
  if (!layer) return;

  const TOTAL = parseInt(layer.dataset.count, 10) || 0;
  if (!TOTAL) return;

  const COLUMN = 1160;   // ширина колонки контента (.wrap max-width)
  const INSET = 12;      // поля не заполняем впритык — по краю и у текста воздух
  const MIN_GUTTER = 110; // уже — стикеры вышли бы мелкими, лучше вообще без них
  const TOP_SAFE = 90;   // под шапкой стикер выглядит обрезанным — начинаем ниже
  // Ячейка раскладки одна и та же по горизонтали и вертикали, поэтому плотность
  // не зависит от ширины экрана: на широком поле просто больше колонок, а не
  // гуще ковёр. При ~330px в экран высотой 1300 попадает около 15 наклеек.
  const CELL = 330;
  const MAX_SIZE = 90;
  const JITTER = 0.7;    // насколько стикер гуляет внутри своей ячейки (0 — центр)
  const MAX_ITEMS = 90;  // предохранитель для очень длинных страниц

  // Один сид на загрузку страницы: раскладка каждый раз новая, но при resize
  // и пересчёте высоты стикеры остаются на своих местах, а не перепрыгивают.
  const seed = (Math.random() * 4294967296) >>> 0;
  function mulberry32(a) {
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // «Мешок» картинок: тянем по одной из перемешанной колоды и,
  // когда она кончается, тасуем заново. Так одна и та же наклейка может
  // встретиться несколько раз, но не два раза подряд в одном углу.
  function makeBag(rand) {
    let bag = [];
    return () => {
      if (!bag.length) {
        bag = Array.from({ length: TOTAL }, (_, i) => i + 1);
        for (let i = bag.length - 1; i > 0; i--) {
          const j = Math.floor(rand() * (i + 1));
          [bag[i], bag[j]] = [bag[j], bag[i]];
        }
      }
      return bag.pop();
    };
  }

  function layout() {
    const vw = document.documentElement.clientWidth;
    const gutter = (vw - COLUMN) / 2;
    if (gutter < MIN_GUTTER) {
      if (layer.childElementCount) layer.replaceChildren();
      return;
    }

    // Высоту берём до вставки; ниже мы держим стикеры внутри неё, поэтому
    // страница от них не удлиняется и пересчёт не зацикливается.
    const docHeight = document.documentElement.scrollHeight;
    const field = gutter - INSET * 2;
    const cols = Math.max(1, Math.min(3, Math.round(field / CELL)));
    const cellW = field / cols;
    const maxSize = Math.min(MAX_SIZE, cellW - 14);
    if (maxSize < 60) { layer.replaceChildren(); return; }

    // Ячейки крупные, поэтому занимаем их все: ровное покрытие даёт сама сетка,
    // а случайность — сдвиг внутри ячейки. Бросать монетку на каждую ячейку
    // нельзя: именно так получаются то кучи, то пустые полосы.
    const rows = Math.ceil((docHeight - TOP_SAFE) / CELL);
    const rand = mulberry32(seed);
    const nextSticker = makeBag(rand);

    const parts = [];
    for (let row = 0; row < rows && parts.length < MAX_ITEMS; row++) {
      for (const side of ["left", "right"]) {
        // Правая сторона идёт на полряда ниже — иначе стикеры слева и справа
        // встают парами на одной высоте и читаются как рамка.
        const rowTop = TOP_SAFE + row * CELL + (side === "right" ? CELL / 2 : 0);

        for (let col = 0; col < cols; col++) {
          const size = Math.round(maxSize * (0.75 + rand() * 0.25));
          // Отсчитываем от центра ячейки и разрешаем гулять только на часть
          // свободного места: соседние стикеры не слипаются на границе ячеек.
          const cx = INSET + col * cellW + (cellW - size) / 2;
          const cy = rowTop + (CELL - size) / 2;
          const x = Math.round(cx + (rand() - 0.5) * (cellW - size) * JITTER);
          const y = Math.round(cy + (rand() - 0.5) * (CELL - size) * JITTER);
          if (y < TOP_SAFE || y + size + 24 > docHeight) continue;
          const angle = (rand() * 2 - 1) * 18;
          const opacity = (0.36 + rand() * 0.22).toFixed(2);
          const src = `/assets/stickers/sticker-${String(nextSticker()).padStart(2, "0")}.png`;
          parts.push(
            `<img class="deco-item" src="${src}" alt="" loading="lazy" decoding="async"` +
            ` style="top:${y}px;${side}:${x}px;width:${size}px;opacity:${opacity};` +
            `transform:rotate(${angle.toFixed(1)}deg)">`
          );
        }
      }
    }
    layer.innerHTML = parts.join("");
  }

  // Пересчитываем на resize и когда страница подрастает (догрузились картинки,
  // раскрылись блоки) — но только на заметное изменение, чтобы не дёргаться.
  let lastHeight = 0;
  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      lastHeight = document.documentElement.scrollHeight;
      layout();
    }, 120);
  }

  layout();
  lastHeight = document.documentElement.scrollHeight;
  window.addEventListener("resize", schedule);
  window.addEventListener("load", schedule);
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (Math.abs(document.documentElement.scrollHeight - lastHeight) > 120) schedule();
    }).observe(document.body);
  }
})();

// Автосабмит форм фильтров при смене любого поля
document.querySelectorAll("form.filters").forEach((form) => {
  form.querySelectorAll("select, input[type=checkbox]").forEach((el) => {
    el.addEventListener("change", () => form.submit());
  });
});

// ── Избранное — только localStorage, без аккаунта и без сервера ──────────
(function () {
  const KEY = "adygid_favorites";

  function readFavorites() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function writeFavorites(list) {
    try {
      localStorage.setItem(KEY, JSON.stringify(list));
    } catch (e) {
      // localStorage недоступен (приватный режим и т.п.) — просто не сохраняем
    }
  }

  function isFavorite(list, type, id) {
    return list.some((f) => f.type === type && f.id === id);
  }

  function paintButton(btn, active) {
    btn.classList.toggle("active", active);
    const label = btn.querySelector(".fav-btn-text");
    if (label) label.textContent = active ? "В избранном" : "В избранное";
  }

  function initButtons() {
    const favorites = readFavorites();
    document.querySelectorAll(".fav-btn").forEach((btn) => {
      const type = btn.dataset.type;
      const id = parseInt(btn.dataset.id, 10);
      paintButton(btn, isFavorite(favorites, type, id));
    });
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".fav-btn");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    const type = btn.dataset.type;
    const id = parseInt(btn.dataset.id, 10);
    let favorites = readFavorites();

    if (isFavorite(favorites, type, id)) {
      favorites = favorites.filter((f) => !(f.type === type && f.id === id));
    } else {
      favorites.push({ type, id });
    }
    writeFavorites(favorites);

    document.querySelectorAll(`.fav-btn[data-type="${type}"][data-id="${id}"]`).forEach((b) => {
      paintButton(b, isFavorite(favorites, type, id));
    });
  });

  initButtons();

  // ── Блок «Избранное» на главной — показываем, только если что-то уже
  // сохранено; пустой раздел никому не нужен и не рендерится вовсе. ──────
  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s || "";
    return div.innerHTML;
  }

  async function renderFavoritesSection() {
    const grid = document.getElementById("favorites-grid");
    const section = document.getElementById("favorites-section");
    if (!grid || !section) return;

    const favorites = readFavorites();
    if (!favorites.length) return;

    const items = favorites.map((f) => `${f.type}:${f.id}`).join(",");
    try {
      const res = await fetch(`/api/site/favorites?items=${encodeURIComponent(items)}`);
      if (!res.ok) throw new Error("bad response");
      const data = await res.json();
      if (!data.length) return;

      grid.innerHTML = data.map((item) => {
        const url = item.kind === "route" ? `/marshruty/${item.id}` : `/mesta/${item.id}`;
        const cover = item.cover ? `background-image:url('${item.cover}')` : "";
        return `<a class="card" href="${url}">
          <div class="cover" style="${cover}"></div>
          <div class="body">
            <h3>${escapeHtml(item.name)}</h3>
            ${item.excerpt ? `<p class="excerpt">${escapeHtml(item.excerpt)}</p>` : ""}
          </div>
        </a>`;
      }).join("");
      section.style.display = "";
    } catch (e) {
      // тихо игнорируем — раздел просто останется скрытым
    }
  }

  renderFavoritesSection();
})();

// ── Лайк «Понравилось» — публичный счётчик на сервере ────────────────────
document.querySelectorAll(".like-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (btn.disabled) return;
    btn.disabled = true;
    const type = btn.dataset.type;
    const id = btn.dataset.id;
    try {
      const res = await fetch(`/api/likes/${type}/${id}`, { method: "POST" });
      if (!res.ok) throw new Error("bad response");
      const data = await res.json();
      btn.classList.toggle("liked", data.liked);
      btn.querySelector(".like-count").textContent = data.count;
    } catch (e) {
      // тихо игнорируем — счётчик просто не обновится
    } finally {
      btn.disabled = false;
    }
  });
});

// ── Оглавление статьи — подсветка раздела, который читают прямо сейчас ────
(() => {
  const headings = Array.from(document.querySelectorAll(".article-toc nav a"))
    .map((link) => ({ link, el: document.getElementById(link.getAttribute("href").slice(1)) }))
    .filter((item) => item.el);
  if (!headings.length) return;

  let queued = false;
  const update = () => {
    queued = false;
    // Порог чуть ниже верха экрана — заголовок считается «текущим», как
    // только подойдёт к этой линии, а не когда упрётся в самый верх.
    const threshold = 130;
    let current = headings[0];
    for (const item of headings) {
      if (item.el.getBoundingClientRect().top - threshold <= 0) current = item;
    }
    headings.forEach((item) => item.link.classList.toggle("active", item === current));
  };
  document.addEventListener("scroll", () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(update);
  }, { passive: true });
  update();
})();

// ── Попап с расшифровкой уровней сложности ────────────────────────────────
document.addEventListener("click", (e) => {
  const infoBtn = e.target.closest(".diff-info-btn");
  document.querySelectorAll(".diff-popover.open").forEach((p) => {
    if (!infoBtn || p !== infoBtn.nextElementSibling) p.classList.remove("open");
  });
  if (infoBtn) {
    e.preventDefault();
    infoBtn.nextElementSibling.classList.toggle("open");
  }
});
