document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector(
        "[data-duplicate-url]"
    );

    if (!form) return;

    const warning = document.getElementById(
        "duplicate-warning"
    );

    const list = document.getElementById(
        "duplicate-list"
    );

    const confirmation = document.getElementById(
        "id_confirm_duplicate"
    );
    const title = document.getElementById("duplicate-title");
    const description = document.getElementById(
        "duplicate-description"
    );
    const confirmBox = document.getElementById(
        "duplicate-confirm-box"
    );
    const saveButton = form.querySelector(
        'button[type="submit"]'
    );

    const fieldNames = [
        "last_name",
        "first_name",
        "middle_name",
        "birth_date",
        "phone"
    ];

    const fields = Object.fromEntries(
        fieldNames.map(name => [
            name,
            document.getElementById(`id_${name}`)
        ])
    );

    let timer;
    let requestVersion = 0;

    function showPatients(patients) {
        list.replaceChildren();

        if (patients.length === 0) {
            warning.hidden = true;
            confirmBox.hidden = false;
            saveButton.disabled = false;
            return;
        }

        const hasExactDuplicate = patients.some(
            patient => patient.is_exact_duplicate
        );

        if (hasExactDuplicate) {
            title.textContent = "Пациент уже зарегистрирован";

            description.textContent =
                "ФИО, дата рождения и телефон полностью совпадают. " +
                "Создание повторной карточки запрещено.";

            confirmBox.hidden = true;
            saveButton.disabled = true;

            if (confirmation) {
                confirmation.checked = false;
            }
        } else {
            title.textContent = "Найдены похожие пациенты";

            description.textContent =
                "Проверьте существующие карточки. " +
                "Если это другой человек, подтвердите регистрацию.";

            confirmBox.hidden = false;
            saveButton.disabled = false;
        }

        for (const patient of patients) {
            const item = document.createElement("li");

            const link = document.createElement("a");
            link.href = patient.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = patient.full_name;

            const details = document.createElement("span");

            let reason = "Возможное совпадение";

            if (patient.is_exact_duplicate) {
                reason = "Полное совпадение";
            } else if (
                patient.same_birth_date &&
                patient.same_phone
            ) {
                reason = "Совпали дата рождения и телефон";
            } else if (patient.same_birth_date) {
                reason = "Совпала дата рождения";
            } else if (patient.same_phone) {
                reason = "Совпал телефон";
            }

            details.textContent =
                ` — ${patient.birth_date}, ` +
                `${patient.phone}. ${reason}`;

            item.append(link, details);
            list.append(item);
        }

        warning.hidden = false;
    }

    function scheduleCheck() {
        clearTimeout(timer);

        const version = ++requestVersion;

        if (confirmation) {
            confirmation.checked = false;
        }

        warning.hidden = true;
        saveButton.disabled = false;
        confirmBox.hidden = false;

        const lastName = fields.last_name.value.trim();
        const firstName = fields.first_name.value.trim();
        const birthDate = fields.birth_date.value.trim();
        const phone = fields.phone.value.trim();

        if (
            !lastName
            || !firstName
            || (!birthDate && !phone)
        ) {
            return;
        }

        timer = setTimeout(async () => {
            const data = new URLSearchParams();

            for (const name of fieldNames) {
                data.append(
                    name,
                    fields[name].value.trim()
                );
            }

            data.append(
                "patient_id",
                form.dataset.patientId || ""
            );

            try {
                const response = await fetch(
                    form.dataset.duplicateUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            "X-CSRFToken": form.querySelector(
                                "[name=csrfmiddlewaretoken]"
                            ).value
                        },
                        body: data
                    }
                );

                if (!response.ok) {
                    throw new Error("Ошибка поиска");
                }

                const result = await response.json();

                // Игнорируем устаревший ответ,
                // если регистратор уже изменил данные.
                if (version !== requestVersion) return;

                showPatients(result.patients);

            } catch (error) {
                if (version !== requestVersion) return;

                list.replaceChildren();
                saveButton.disabled = false;
                confirmBox.hidden = true;

                const item = document.createElement("li");
                item.textContent =
                    "Не удалось проверить совпадения. "
                    + "Проверка повторится при сохранении.";

                list.append(item);
                warning.hidden = false;
            }
        }, 400);
    }

    for (const field of Object.values(fields)) {
        if (!field) return;

        field.addEventListener(
            "input",
            scheduleCheck
        );

        field.addEventListener(
            "change",
            scheduleCheck
        );
    }
});