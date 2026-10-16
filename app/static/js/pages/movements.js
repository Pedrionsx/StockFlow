(() => {
  const form = document.querySelector("#movement-form");
  const productSelect = document.querySelector("#movement-product");
  const currentStock = document.querySelector("#movement-current-stock");
  const quantity = document.querySelector("#movement-quantity");
  const submitButton = document.querySelector("#movement-submit");
  const feedback = document.querySelector("#movement-feedback");
  const historyBody = document.querySelector("#movement-history");
  const historyCount = document.querySelector("#movement-history-count");
  const historySearch = document.querySelector("#history-search");
  const historyType = document.querySelector("#history-type");
  const historyDateStart = document.querySelector("#history-date-start");
  const historyDateEnd = document.querySelector("#history-date-end");
  const previousPage = document.querySelector("#history-previous");
  const nextPage = document.querySelector("#history-next");
  const pageIndicator = document.querySelector("#history-page-indicator");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

  if (!form || !productSelect || !currentStock || !quantity || !submitButton || !feedback || !historyBody || !csrfToken) {
    return;
  }

  let products = [];
  const historyState = { page: 1, pageSize: 10, sort: "data", direction: "desc" };
  let historyRequest = 0;
  let searchTimer;

  const showFeedback = (message, success = false) => {
    feedback.textContent = message;
    feedback.classList.toggle("is-success", success);
    feedback.classList.toggle("is-error", !success);
    feedback.hidden = false;
    window.StockFlowToast?.show(message, success ? "success" : "error");
  };

  const selectedOperation = () => form.querySelector('input[name="tipo"]:checked')?.value ?? "ENTRADA";

  const updateSubmitLabel = () => {
    submitButton.textContent = selectedOperation() === "ENTRADA" ? "Registrar entrada" : "Registrar saída";
  };

  const updateSelectedStock = () => {
    const product = products.find((item) => String(item.id) === productSelect.value);
    currentStock.textContent = product
      ? `Estoque atual: ${product.estoque_atual} un.`
      : "Selecione um produto para consultar o saldo.";
    if (product) {
      quantity.max = String(product.estoque_atual || "");
    } else {
      quantity.removeAttribute("max");
    }
  };

  const loadProducts = async () => {
    const pageSize = 100;
    let offset = 0;
    let total = 0;
    let hasMore = false;
    products = [];
    do {
      const response = await fetch(`/api/produtos?limit=${pageSize}&offset=${offset}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        throw new Error(result.message || "Não foi possível carregar os produtos.");
      }
      products.push(...result.data);
      total = result.pagination.total;
      offset += result.data.length;
      hasMore = result.data.length === pageSize && offset < total;
    } while (hasMore);

    productSelect.replaceChildren(new Option(
      products.length ? "Selecione um produto" : "Nenhum produto ativo disponível",
      "",
    ));
    products.forEach((product) => {
      productSelect.add(new Option(
        `${product.nome} · ${product.codigo_barras}`,
        String(product.id),
      ));
    });
    productSelect.disabled = products.length === 0;
    submitButton.disabled = products.length === 0;
    updateSelectedStock();
  };

  const createCell = (tag, text, className) => {
    const cell = document.createElement(tag);
    cell.textContent = text;
    if (className) cell.className = className;
    return cell;
  };

  const showHistoryError = (error) => {
    historyBody.replaceChildren();
    const row = document.createElement("tr");
    const cell = createCell("td", error.message || "Não foi possível carregar o histórico.", "movement-error");
    cell.colSpan = 5;
    row.append(cell);
    historyBody.append(row);
    historyCount.textContent = "Falha ao carregar o histórico";
    showFeedback(
      error instanceof TypeError
        ? "Falha de comunicação com o servidor. Tente novamente."
        : error.message || "Não foi possível carregar o histórico.",
    );
  };

  const renderMovements = (movements) => {
    historyBody.replaceChildren();
    if (!movements.length) {
      const row = document.createElement("tr");
      const cell = createCell("td", "Ainda não há movimentações registradas.", "movement-empty");
      cell.colSpan = 5;
      row.append(cell);
      historyBody.append(row);
      return;
    }

    movements.forEach((movement) => {
      const row = document.createElement("tr");
      const productCell = document.createElement("td");
      const productInfo = document.createElement("span");
      productInfo.className = "movement-product-cell";
      productInfo.append(
        createCell("strong", movement.produto),
        createCell("span", movement.codigo_barras),
      );
      productCell.append(productInfo);

      const typeCell = document.createElement("td");
      const type = createCell(
        "span",
        movement.tipo === "ENTRADA" ? "Entrada" : "Saída",
        `movement-kind ${movement.tipo === "ENTRADA" ? "is-entry" : "is-exit"}`,
      );
      typeCell.append(type);

      const sign = movement.tipo === "ENTRADA" ? "+" : "−";
      const quantityCell = createCell(
        "td",
        `${sign} ${movement.quantidade} un. · saldo ${movement.estoque_atual}`,
        "movement-quantity",
      );

      const actorCell = document.createElement("td");
      actorCell.append(createCell("span", movement.usuario, "movement-actor-name"));
      const date = new Date(movement.data);
      const formattedDate = Number.isNaN(date.getTime())
        ? movement.data
        : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
      const dateCell = createCell("td", formattedDate, "movement-date");

      row.append(productCell, typeCell, quantityCell, actorCell, dateCell);
      historyBody.append(row);
    });
  };

  const loadHistory = async () => {
    const requestId = ++historyRequest;
    historyBody.replaceChildren();
    const loadingRow = document.createElement("tr");
    const loadingCell = createCell("td", "Carregando histórico...", "movement-loading");
    loadingCell.colSpan = 5;
    loadingRow.append(loadingCell);
    historyBody.append(loadingRow);

    const params = new URLSearchParams({
      page: String(historyState.page),
      page_size: String(historyState.pageSize),
      sort: historyState.sort,
      direction: historyState.direction,
      q: historySearch?.value.trim() || "",
      tipo: historyType?.value || "",
      data_inicio: historyDateStart?.value || "",
      data_fim: historyDateEnd?.value || "",
    });
    const response = await fetch(`/api/movimentacoes?${params}`, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.message || "Não foi possível carregar o histórico.");
    }
    if (requestId !== historyRequest) return;
    renderMovements(result.data);
    const { page, page_size: pageSize, total, total_pages: totalPages } = result.pagination;
    const firstItem = total === 0 ? 0 : (page - 1) * pageSize + 1;
    const lastItem = Math.min(page * pageSize, total);
    historyCount.textContent = total === 0
      ? "Nenhuma movimentação encontrada"
      : `Exibindo ${firstItem}–${lastItem} de ${total} movimentações`;
    pageIndicator.textContent = `Página ${page} de ${Math.max(totalPages, 1)}`;
    previousPage.disabled = page <= 1;
    nextPage.disabled = page >= totalPages;
    document.querySelectorAll("[data-sort]").forEach((button) => {
      const active = button.dataset.sort === historyState.sort;
      button.querySelector("span").textContent = active
        ? historyState.direction === "asc" ? "↑" : "↓"
        : "";
      button.closest("th")?.setAttribute("aria-sort", active
        ? historyState.direction === "asc" ? "ascending" : "descending"
        : "none");
    });
  };

  const loadPageData = async () => {
    try {
      await Promise.all([loadProducts(), loadHistory()]);
    } catch (error) {
      showFeedback(
        error instanceof TypeError
          ? "Falha de comunicação com o servidor. Tente novamente."
          : error.message || "Falha de comunicação com o servidor.",
      );
      if (!products.length) {
        productSelect.replaceChildren(new Option("Falha ao carregar produtos", ""));
        productSelect.disabled = true;
        submitButton.disabled = true;
      }
      historyBody.replaceChildren();
      const row = document.createElement("tr");
      const cell = createCell("td", error.message || "Falha ao carregar o histórico.", "movement-error");
      cell.colSpan = 5;
      row.append(cell);
      historyBody.append(row);
    }
  };

  form.querySelectorAll('input[name="tipo"]').forEach((radio) => {
    radio.addEventListener("change", updateSubmitLabel);
  });
  productSelect.addEventListener("change", updateSelectedStock);
  document.querySelector("#history-refresh")?.addEventListener("click", () => {
    loadHistory().catch(showHistoryError);
  });
  historySearch?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      historyState.page = 1;
      loadHistory().catch(showHistoryError);
    }, 250);
  });
  historyType?.addEventListener("change", () => {
    historyState.page = 1;
    loadHistory().catch(showHistoryError);
  });
  [historyDateStart, historyDateEnd].forEach((input) => {
    input?.addEventListener("change", () => {
      historyState.page = 1;
      loadHistory().catch(showHistoryError);
    });
  });
  previousPage?.addEventListener("click", () => {
    if (historyState.page <= 1) return;
    historyState.page -= 1;
    loadHistory().catch(showHistoryError);
  });
  nextPage?.addEventListener("click", () => {
    historyState.page += 1;
    loadHistory().catch(showHistoryError);
  });
  document.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      if (historyState.sort === button.dataset.sort) {
        historyState.direction = historyState.direction === "asc" ? "desc" : "asc";
      } else {
        historyState.sort = button.dataset.sort;
        historyState.direction = "asc";
      }
      historyState.page = 1;
      loadHistory().catch(showHistoryError);
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.hidden = true;
    const operation = selectedOperation();
    const payload = {
      produto_id: Number(productSelect.value),
      quantidade: Number(quantity.value),
      observacao: form.elements.observacao.value.trim() || null,
    };
    submitButton.disabled = true;
    try {
      const response = await fetch(
        operation === "ENTRADA" ? "/api/movimentacoes/entradas" : "/api/movimentacoes/saidas",
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
          },
          body: JSON.stringify(payload),
        },
      );
      const result = await response.json();
      if (!response.ok || !result.success) {
        const fieldErrors = result.errors ? Object.values(result.errors).flat().join(" ") : "";
        throw new Error([result.message, fieldErrors].filter(Boolean).join(" "));
      }

      const successMessage = `${result.message} Saldo atual: ${result.data.estoque_atual} un.`;
      showFeedback(successMessage, true);
      form.reset();
      form.querySelector('input[name="tipo"][value="ENTRADA"]').checked = true;
      updateSubmitLabel();
      try {
        await Promise.all([loadProducts(), loadHistory()]);
      } catch (refreshError) {
        showFeedback(
          `${successMessage} A movimentação foi salva, mas a tela não pôde atualizar. Atualize os dados antes de tentar novamente.`,
          true,
        );
        throw refreshError;
      }
    } catch (error) {
      if (feedback.classList.contains("is-success")) {
        console.error("Movimentação salva, mas a atualização da tela falhou.", error);
      } else {
        showFeedback(
          error instanceof TypeError
            ? "Falha de comunicação com o servidor. Tente novamente."
            : error.message || "Não foi possível registrar a movimentação.",
        );
      }
    } finally {
      submitButton.disabled = products.length === 0;
    }
  });

  updateSubmitLabel();
  loadPageData();
})();
