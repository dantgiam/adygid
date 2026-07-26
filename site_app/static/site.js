// Случайное место/маршрут — прогрессивное улучшение поверх серверного рендера.
(function () {
  const card = document.getElementById("highlight-card");
  const btn = document.getElementById("regenerate-btn");
  if (!btn || !card) return;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Ищу...";
    try {
      const res = await fetch("/api/site/random");
      if (!res.ok) throw new Error("bad response");
      const data = await res.json();
      if (!data) return;

      card.querySelector(".hl-tag").textContent = data.tag_label;
      card.querySelector(".hl-cover").style.backgroundImage = data.cover
        ? `url('${data.cover}')`
        : "";
      card.querySelector("h3").textContent = data.name;
      card.querySelector("p").textContent = data.excerpt || "";
      const link = card.querySelector(".hl-open");
      link.href = data.url;
    } catch (e) {
      // тихо игнорируем — карточка просто останется прежней
    } finally {
      btn.disabled = false;
      btn.textContent = "Перегенерировать";
    }
  });
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
