(() => {
  document.querySelectorAll("form").forEach((form) => {
    if (form.method.toUpperCase() !== "POST" || form.dataset.async === "true") return;
    const fields = [...form.querySelectorAll("input, select, textarea")];
    const invalidFields = fields.filter((field) =>
      field.closest(".form-field")?.querySelector(".field-error"),
    );

    invalidFields.forEach((field, index) => {
      const group = field.closest(".form-field");
      const errors = [...group.querySelectorAll(".field-error")];
      errors.forEach((error, errorIndex) => {
        if (!error.id) error.id = `${field.id || "field"}-error-${errorIndex + 1}`;
      });
      field.setAttribute("aria-invalid", "true");
      field.setAttribute("aria-describedby", errors.map((error) => error.id).join(" "));
      field.classList.add("is-invalid");
      field.addEventListener("input", () => clearFieldError(field), { once: true });
      field.addEventListener("change", () => clearFieldError(field), { once: true });
      if (index === 0) window.setTimeout(() => field.focus(), 0);
    });

    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented) return;
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
        return;
      }
      const submitter = event.submitter || form.querySelector('[type="submit"]');
      if (!submitter || submitter.disabled) {
        event.preventDefault();
        return;
      }
      submitter.disabled = true;
      submitter.dataset.originalLabel = submitter.textContent;
      submitter.textContent = "Salvando...";
    });
  });

  function clearFieldError(field) {
    const group = field.closest(".form-field");
    group?.querySelectorAll(".field-error").forEach((error) => error.remove());
    field.removeAttribute("aria-invalid");
    field.removeAttribute("aria-describedby");
    field.classList.remove("is-invalid");
  }
})();
