document.addEventListener("DOMContentLoaded", () => {
  const menu = document.querySelector("[data-menu]");
  const sidebar = document.querySelector("#sidebar");
  menu?.addEventListener("click", () => sidebar?.classList.toggle("open"));

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll("[data-panel]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.querySelector(`[data-panel="${button.dataset.tab}"]`)?.classList.add("active");
    });
  });

  document.querySelectorAll("[data-validate]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (event.submitter?.value === "search") return;
      form.querySelectorAll(".client-error").forEach((node) => node.remove());
      form.querySelectorAll("[required]").forEach((field) => {
        field.classList.remove("input-invalid");
        if (!field.value && field.type !== "radio") {
          event.preventDefault();
          field.classList.add("input-invalid");
          const error = document.createElement("small");
          error.className = "client-error";
          error.textContent = "Заполните это поле.";
          field.insertAdjacentElement("afterend", error);
        }
      });
    });
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = button.closest(".login-input-shell")?.querySelector("input");
    button.addEventListener("click", () => {
      if (!input) return;
      const passwordIsVisible = input.type === "text";
      input.type = passwordIsVisible ? "password" : "text";
      button.setAttribute("aria-pressed", String(!passwordIsVisible));
      button.setAttribute("aria-label", passwordIsVisible ? "Показать пароль" : "Скрыть пароль");
      input.focus();
    });
  });

  const passwordHelpButton = document.querySelector("[data-password-help]");
  const passwordHelpText = document.querySelector("[data-password-help-text]");
  passwordHelpButton?.addEventListener("click", () => {
    if (!passwordHelpText) return;
    passwordHelpText.hidden = !passwordHelpText.hidden;
  });
});
