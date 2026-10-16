(() => {
  const container = document.querySelector("#toast-container");
  if (!container) return;

  const maxToasts = 4;
  const defaultDuration = 5000;
  const icons = {
    success: "✓",
    error: "!",
    warning: "!",
    info: "i",
  };
  const types = new Set(Object.keys(icons));

  const removeToast = (toast) => {
    if (!toast.isConnected || toast.dataset.removing === "true") return;
    toast.dataset.removing = "true";
    window.clearTimeout(toast.dismissTimer);
    toast.classList.add("is-leaving");
    toast.addEventListener("transitionend", () => toast.remove(), { once: true });
    window.setTimeout(() => toast.remove(), 250);
  };

  const showToast = (message, type = "info", duration = defaultDuration) => {
    if (typeof message !== "string" || !message.trim()) return null;
    const normalizedType = types.has(type) ? type : "info";

    while (container.children.length >= maxToasts) {
      removeToast(container.firstElementChild);
      if (container.children.length >= maxToasts) {
        container.firstElementChild?.remove();
      }
    }

    const toast = document.createElement("div");
    toast.className = `toast toast--${normalizedType}`;
    toast.setAttribute("role", normalizedType === "error" ? "alert" : "status");
    toast.dataset.removing = "false";

    const icon = document.createElement("span");
    icon.className = "toast__icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = icons[normalizedType];

    const text = document.createElement("span");
    text.className = "toast__message";
    text.textContent = message.trim();

    const close = document.createElement("button");
    close.className = "toast__close";
    close.type = "button";
    close.setAttribute("aria-label", "Dispensar notificação");
    close.textContent = "×";
    close.addEventListener("click", () => removeToast(toast));

    toast.append(icon, text, close);
    container.append(toast);
    requestAnimationFrame(() => toast.classList.add("is-visible"));

    const timeout = Number(duration);
    if (Number.isFinite(timeout) && timeout > 0) {
      toast.dismissTimer = window.setTimeout(() => removeToast(toast), timeout);
    }
    return toast;
  };

  const initialMessages = [...document.querySelectorAll("[data-toast-initial]")];
  initialMessages.forEach((item) => {
    const category = item.dataset.toastType;
    const type = category === "success"
      ? "success"
      : ["error", "danger"].includes(category)
        ? "error"
        : category === "warning"
          ? "warning"
          : "info";
    showToast(item.dataset.toastMessage, type);
    item.remove();
  });

  window.StockFlowToast = Object.freeze({ show: showToast });
  document.addEventListener("stockflow:toast", (event) => {
    const { message, type, duration } = event.detail || {};
    showToast(message, type, duration);
  });
})();
