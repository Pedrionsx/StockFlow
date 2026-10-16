(() => {
  const sidebar = document.querySelector("#app-sidebar");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const backdrop = document.querySelector("[data-sidebar-close]");

  if (sidebar && toggle && backdrop) {
    const setSidebarOpen = (open) => {
      sidebar.classList.toggle("is-open", open);
      backdrop.classList.toggle("is-visible", open);
      document.body.classList.toggle("sidebar-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
    };

    toggle.addEventListener("click", () => {
      setSidebarOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    backdrop.addEventListener("click", () => setSidebarOpen(false));
    sidebar.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setSidebarOpen(false));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setSidebarOpen(false);
        toggle.focus();
      }
    });
    window.matchMedia("(min-width: 761px)").addEventListener("change", () => setSidebarOpen(false));
  }

  const shell = document.querySelector(".app-shell");
  const compactToggle = document.querySelector("[data-sidebar-collapse-toggle]");
  if (shell && compactToggle) {
    compactToggle.addEventListener("click", () => {
      const collapsed = shell.classList.toggle("sidebar-collapsed");
      compactToggle.setAttribute("aria-expanded", String(!collapsed));
      compactToggle.setAttribute("aria-label", collapsed ? "Expandir menu" : "Recolher menu");
    });
  }

  window.addEventListener("resize", () => {
    if (window.innerWidth <= 1050 && window.innerWidth > 760) return;
    shell?.classList.remove("sidebar-collapsed");
    if (compactToggle) {
      compactToggle.setAttribute("aria-expanded", "true");
      compactToggle.setAttribute("aria-label", "Recolher menu");
    }
  });

  const date = document.querySelector("#current-date");
  if (date) {
    date.textContent = new Intl.DateTimeFormat("pt-BR", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(new Date());
  }
})();
