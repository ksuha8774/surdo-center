from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required
from scheduling.models import Appointment
from .forms import MedicalVisitForm
from .models import MedicalVisit
from .configurations import visit_configuration


def _format_age(age):
    if 11 <= age % 100 <= 14:
        suffix = "лет"
    elif age % 10 == 1:
        suffix = "год"
    elif 2 <= age % 10 <= 4:
        suffix = "года"
    else:
        suffix = "лет"
    return f"{age} {suffix}"


@role_required(User.Role.DOCTOR)
@transaction.atomic
def visit_edit(request, appointment_pk):
    appointment = get_object_or_404(Appointment.objects.select_for_update(of=("self",)).select_related("patient", "doctor", "planned_service"), pk=appointment_pk)
    if appointment.doctor_id != request.user.id:
        raise PermissionDenied("Нельзя открыть приём другого врача.")
    if appointment.status in (Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW):
        raise PermissionDenied("Для отменённой записи или неявки приём недоступен.")

    visit, _ = MedicalVisit.objects.get_or_create(appointment=appointment)
    config = visit_configuration(visit)
    if not visit.form_snapshot:
        visit.form_type = config["code"]
        visit.form_version = config["version"]
        visit.form_snapshot = config
        visit.save(update_fields=("form_type", "form_version", "form_snapshot"))
    if appointment.status == Appointment.Status.PLANNED:
        appointment.status = Appointment.Status.IN_PROGRESS
        appointment.save(update_fields=("status", "updated_at"))

    is_completed = appointment.status == Appointment.Status.COMPLETED or visit.completed_at is not None
    if request.method == "POST" and is_completed:
        raise PermissionDenied("Завершённый приём недоступен для редактирования.")

    form = MedicalVisitForm(request.POST or None, instance=visit)
    if request.method == "POST" and request.POST.get("audiometry") and "audiometry" not in config["modules"]:
        raise PermissionDenied("Аудиометрия не предусмотрена формой этой услуги.")
    if is_completed:
        for field in form.fields.values():
            field.disabled = True

    if request.method == "POST" and form.is_valid():
        visit = form.save(commit=False)
        if request.POST.get("complete"):
            visit.completed_at = timezone.now()
            appointment.status = Appointment.Status.COMPLETED
            appointment.save(update_fields=("status", "updated_at"))
            messages.success(request, "Приём завершён, заключение сохранено.")
        elif request.POST.get("audiometry"):
            visit.save()
            existing_exam = visit.audiometry_exams.order_by("-created_at", "-pk").first()
            if existing_exam:
                return redirect("audiometry:detail", pk=existing_exam.pk)
            return redirect("audiometry:create_for_visit", visit_pk=visit.pk)
        else:
            messages.success(request, "Черновик приёма сохранён.")
        visit.save()
        return redirect("scheduling:detail", pk=appointment.pk)

    existing_exam = visit.audiometry_exams.order_by("-created_at", "-pk").first()
    today = timezone.localdate()
    born = appointment.patient.birth_date
    patient_age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return render(request, "medical/visit_form.html", {
        "appointment": appointment,
        "visit": visit,
        "form": form,
        "patient_age_label": _format_age(patient_age),
        "is_completed": is_completed,
        "existing_exam": existing_exam,
        "visit_config": config,
        "form_sections": form.rendered_sections,
        "has_audiometry": "audiometry" in config["modules"],
        "has_exam_history": "exam_history" in config["modules"],
    })
