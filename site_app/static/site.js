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
})();

// ── Лайк «Пригодилось» — публичный счётчик на сервере ────────────────────
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
