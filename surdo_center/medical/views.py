from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required
from scheduling.models import Appointment
from .forms import MedicalVisitForm
from .models import MedicalVisit


@role_required(User.Role.DOCTOR)
def visit_edit(request, appointment_pk):
    appointment = get_object_or_404(Appointment.objects.select_related("patient", "doctor", "planned_service"), pk=appointment_pk)
    if appointment.doctor_id != request.user.id:
        raise PermissionDenied("Нельзя открыть приём другого врача.")
    if appointment.status in (Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW):
        raise PermissionDenied("Для отменённой записи или неявки приём недоступен.")

    visit, _ = MedicalVisit.objects.get_or_create(appointment=appointment)
    if appointment.status == Appointment.Status.PLANNED:
        appointment.status = Appointment.Status.IN_PROGRESS
        appointment.save(update_fields=("status", "updated_at"))

    form = MedicalVisitForm(request.POST or None, instance=visit)
    if request.method == "POST" and form.is_valid():
        visit = form.save(commit=False)
        if request.POST.get("complete"):
            visit.completed_at = timezone.now()
            appointment.status = Appointment.Status.COMPLETED
            appointment.save(update_fields=("status", "updated_at"))
            messages.success(request, "Приём завершён, заключение сохранено.")
        else:
            messages.success(request, "Черновик приёма сохранён.")
        visit.save()
        return redirect("scheduling:detail", pk=appointment.pk)

    previous_visits = MedicalVisit.objects.filter(
        appointment__patient=appointment.patient,
        appointment__status=Appointment.Status.COMPLETED,
    ).exclude(pk=visit.pk).select_related("appointment").order_by("-appointment__appointment_date")[:5]
    return render(request, "medical/visit_form.html", {
        "appointment": appointment, "visit": visit, "form": form, "previous_visits": previous_visits,
    })
