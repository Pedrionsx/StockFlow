(() => {
  const input = document.querySelector("#product-search-input");
  const clearButton = document.querySelector("#product-search-clear");
  const emptyTitle = document.querySelector("#products-empty-title");
  const emptyMessage = document.querySelector("#products-empty-message");
  const emptyRow = document.querySelector("#products-empty-row");
  const resultCount = document.querySelector("#products-result-count");
  const rows = [...document.querySelectorAll("[data-product-row]")];
  if (!input || !clearButton || !emptyRow || !resultCount) return;

  const initialCount = rows.length;
  const update = () => {
    const query = input.value.trim().toLocaleLowerCase();
    let visibleCount = 0;
    rows.forEach((row) => {
      const matches = row.dataset.search.includes(query);
      row.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    clearButton.hidden = input.value.length === 0;
    emptyRow.hidden = visibleCount > 0;
    if (emptyTitle && emptyMessage) {
      emptyTitle.textContent = visibleCount === 0 && query
        ? "Nenhum resultado encontrado"
        : "Nenhum produto encontrado";
      emptyMessage.textContent = visibleCount === 0 && query
        ? "Tente outro nome, código de barras ou categoria."
        : initialCount === 0
          ? "Não há produtos nesta visualização."
          : "Não há produtos para exibir.";
    }
    resultCount.textContent = `${visibleCount} ${visibleCount === 1 ? "produto encontrado" : "produtos encontrados"}`;
  };

  input.addEventListener("input", update);
  clearButton.addEventListener("click", () => {
    input.value = "";
    input.focus();
    update();
  });
  update();
})();
