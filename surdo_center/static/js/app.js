document.addEventListener("DOMContentLoaded", () => {
  const menu = document.querySelector("[data-menu]");
  const navigation = document.querySelector("#primary-navigation");
  const closeNavigation = () => {
    navigation?.classList.remove("open");
    menu?.setAttribute("aria-expanded", "false");
  };
  menu?.addEventListener("click", () => {
    const isOpen = navigation?.classList.toggle("open") ?? false;
    menu.setAttribute("aria-expanded", String(isOpen));
  });
  navigation?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeNavigation));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNavigation();
  });

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

  document.querySelectorAll("[data-slot-form]").forEach((form) => {
    const mode = form.dataset.slotMode;
    const endpoint = form.dataset.slotUrl;
    const doctor = form.querySelector("[name='doctor']");
    const service = form.querySelector("[name='service']");
    const appointmentDate = form.querySelector("[name='appointment_date']");
    const grid = form.querySelector("[data-slot-grid]");
    const message = form.querySelector("[data-slot-message]");
    const submit = form.querySelector("[data-slot-submit]");
    let activeRequest;

    const setMessage = (text, state = "") => {
      if (!message) return;
      message.textContent = text;
      message.classList.toggle("has-slots", state === "success");
      message.classList.toggle("is-loading", state === "loading");
      message.classList.toggle("is-error", state === "error");
    };

    const clearSlots = () => {
      grid?.replaceChildren();
      if (submit) submit.disabled = true;
    };

    const renderSlots = (payload) => {
      clearSlots();
      (payload.slots || []).forEach((slot) => {
        const label = document.createElement("label");
        label.className = "slot";

        const input = document.createElement("input");
        input.type = "radio";
        input.name = "slot";
        input.value = slot.start;
        input.required = true;

        const card = document.createElement("span");
        const start = document.createElement("b");
        const end = document.createElement("small");
        start.textContent = slot.start;
        end.textContent = `до ${slot.end}`;
        card.append(start, end);
        label.append(input, card);
        grid?.append(label);
      });
      const hasSlots = Boolean(payload.slots?.length);
      if (submit) submit.disabled = !hasSlots;
      setMessage(payload.message || (hasSlots ? "Выберите время начала." : "Свободных интервалов нет."), hasSlots ? "success" : "");
    };

    const refreshSlots = async () => {
      const dateValue = appointmentDate?.value;
      const selectionComplete = mode === "reschedule"
        ? Boolean(dateValue)
        : Boolean(doctor?.value && service?.value && dateValue);
      if (!selectionComplete) {
        activeRequest?.abort();
        clearSlots();
        setMessage(mode === "reschedule"
          ? "Выберите новую дату. Время обновится автоматически."
          : "Выберите врача, услугу и дату. Время обновится автоматически.");
        return;
      }

      activeRequest?.abort();
      activeRequest = new AbortController();
      clearSlots();
      setMessage("Проверяем свободное время…", "loading");
      const url = new URL(endpoint, window.location.href);
      url.searchParams.set("date", dateValue);
      if (mode === "create") {
        url.searchParams.set("doctor", doctor.value);
        url.searchParams.set("service", service.value);
      }

      try {
        const response = await fetch(url, {
          headers: {"X-Requested-With": "XMLHttpRequest"},
          signal: activeRequest.signal,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.message || "Не удалось получить свободное время.");
        renderSlots(payload);
      } catch (error) {
        if (error.name === "AbortError") return;
        clearSlots();
        setMessage(error.message || "Не удалось обновить расписание. Повторите попытку.", "error");
      }
    };

    [doctor, service, appointmentDate].filter(Boolean).forEach((field) => {
      field.addEventListener("change", refreshSlots);
    });
    form.addEventListener("submit", (event) => {
      if (!["book", "move"].includes(event.submitter?.value)) return;
      if (!form.querySelector("input[name='slot']:checked")) {
        event.preventDefault();
        setMessage("Выберите один из доступных интервалов.", "error");
      }
    });
    refreshSlots();
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
