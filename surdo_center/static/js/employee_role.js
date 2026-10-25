document.addEventListener("DOMContentLoaded", function () {
    const role = document.getElementById("id_role");
    const specialization = document.getElementById("id_specialization");

    if (!role || !specialization) {
        return;
    }

    const row = specialization.closest(".form-row");

    if (!row) {
        return;
    }

    function updateSpecialization() {
        const isDoctor = role.value === "doctor";
        const hasError = row.querySelector(".errorlist") !== null;

        row.style.display = (isDoctor || hasError) ? "" : "none";
    }

    role.addEventListener("change", function () {
        if (role.value !== "doctor") {
            specialization.value = "";
        }

        updateSpecialization();
    });

    updateSpecialization();
});