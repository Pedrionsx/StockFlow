(() => {
  let activeModal = null;
  let previousFocus = null;

  const focusableElements = (modal) => [...modal.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hidden);

  const closeModal = (modal = activeModal) => {
    if (!modal || modal !== activeModal) return;
    modal.hidden = true;
    activeModal = null;
    previousFocus?.focus();
    previousFocus = null;
  };

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-modal-open]");
    if (opener) {
      const modal = document.getElementById(opener.dataset.modalOpen);
      if (!modal) return;
      if (activeModal) closeModal();
      previousFocus = opener;
      activeModal = modal;
      modal.hidden = false;
      focusableElements(modal)[0]?.focus();
      modal.dispatchEvent(new CustomEvent("modal:open", { detail: { trigger: opener } }));
      return;
    }

    const closeButton = event.target.closest("[data-modal-close]");
    if (closeButton && activeModal?.contains(closeButton)) {
      closeModal();
      return;
    }

    if (event.target === activeModal) closeModal();
  });

  document.addEventListener("modal:close", () => closeModal());

  document.addEventListener("keydown", (event) => {
    if (!activeModal) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = focusableElements(activeModal);
    if (!focusable.length) {
      event.preventDefault();
      activeModal.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
