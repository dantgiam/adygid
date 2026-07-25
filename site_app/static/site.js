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
