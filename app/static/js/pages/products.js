(() => {
  const form = document.querySelector("#stock-movement-form");
  const modal = document.querySelector("#stock-movement-modal");
  const submitButton = document.querySelector("#stock-modal-submit");
  const feedback = document.querySelector("#stock-modal-feedback");
  const productLabel = document.querySelector("#stock-modal-product");
  const currentStock = document.querySelector("#stock-modal-current");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
  if (!form || !modal || !submitButton || !feedback || !csrfToken) return;

  let activeTrigger = null;
  let closeTimer;
  const showFeedback = (message, success = false) => {
    feedback.textContent = message;
    feedback.classList.toggle("is-success", success);
    feedback.classList.toggle("is-error", !success);
    feedback.hidden = false;
    window.StockFlowToast?.show(
      message,
      success ? "success" : "error",
    );
  };

  const updateProductRow = (productId, stock) => {
    const row = document.querySelector(`[data-product-row][data-product-id="${CSS.escape(String(productId))}"]`);
    if (!row) return;
    row.dataset.quantity = String(stock);
    const minimum = Number(row.dataset.minimum);
    const quantityBadge = row.querySelector("[data-product-quantity]");
    quantityBadge.textContent = `${stock} un.`;
    quantityBadge.classList.toggle("is-low", stock <= minimum);
    row.querySelectorAll("[data-product-id]").forEach((button) => {
      button.dataset.productQuantity = String(stock);
    });
    const search = document.querySelector("#product-search-input");
    if (search) search.dispatchEvent(new Event("input"));
  };

  modal.addEventListener("modal:open", (event) => {
    window.clearTimeout(closeTimer);
    activeTrigger = event.detail.trigger;
    const { productId, productName, productCode, productQuantity, productMinimum, movementType } = activeTrigger.dataset;
    const isEntry = movementType === "ENTRADA";
    form.elements.produto_id.value = productId;
    form.elements.tipo.value = movementType;
    form.elements.quantidade.value = "";
    form.elements.observacao.value = "";
    form.elements.quantidade.removeAttribute("max");
    submitButton.textContent = isEntry ? "Registrar entrada" : "Registrar saída";
    productLabel.textContent = `${productName} · ${productCode}`;
    currentStock.textContent = `Estoque atual: ${productQuantity} un. · Mínimo: ${productMinimum} un.`;
    feedback.hidden = true;
    feedback.textContent = "";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    const movementType = form.elements.tipo.value;
    const quantity = Number(form.elements.quantidade.value);
    if (!Number.isSafeInteger(quantity) || quantity < 1) {
      showFeedback("Informe uma quantidade inteira maior que zero.");
      return;
    }
    if (
      movementType === "SAIDA"
      && quantity > Number(activeTrigger?.dataset.productQuantity || 0)
    ) {
      showFeedback(
        "Não foi possível registrar a saída: o estoque disponível é inferior à quantidade solicitada.",
      );
      return;
    }

    submitButton.disabled = true;
    feedback.hidden = true;
    try {
      const endpoint = movementType === "ENTRADA"
        ? "/api/movimentacoes/entradas"
        : "/api/movimentacoes/saidas";
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          produto_id: Number(form.elements.produto_id.value),
          quantidade: quantity,
          observacao: form.elements.observacao.value.trim() || null,
        }),
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        const errors = result.errors ? Object.values(result.errors).flat().join(" ") : "";
        throw new Error([result.message, errors].filter(Boolean).join(" "));
      }

      updateProductRow(result.data.produto_id, result.data.estoque_atual);
      document.dispatchEvent(new CustomEvent("stock:movement-saved", { detail: result.data }));
      showFeedback(`${result.message} Saldo atual: ${result.data.estoque_atual} un.`, true);
      closeTimer = window.setTimeout(() => {
        if (!modal.hidden) document.dispatchEvent(new CustomEvent("modal:close"));
      }, 900);
    } catch (error) {
      showFeedback(
        error instanceof TypeError
          ? "Falha de comunicação com o servidor. Tente novamente."
          : error.message || "Não foi possível registrar a movimentação.",
      );
    } finally {
      submitButton.disabled = false;
    }
  });
})();
