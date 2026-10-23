from datetime import time

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required
from .forms import AppointmentWizardForm, RescheduleForm
from .models import Appointment, DoctorScheduleTemplate
from .services import create_appointment, get_available_slots, move_appointment


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def appointment_list(request):
    appointments = Appointment.objects.select_related("patient", "doctor", "planned_service")
    if request.user.role == User.Role.DOCTOR:
        appointments = appointments.filter(doctor=request.user)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        appointments = appointments.filter(Q(patient__last_name__icontains=query) | Q(patient__phone__icontains=query))
    if status:
        appointments = appointments.filter(status=status)
    return render(request, "scheduling/appointment_list.html", {
        "appointments": appointments.order_by("-appointment_date", "-start_time")[:150],
        "statuses": Appointment.Status.choices,
        "query": query,
        "selected_status": status,
    })


@role_required(User.Role.ADMINISTRATOR)
def appointment_create(request):
    data = request.POST if request.method == "POST" else None
    initial = {"patient": request.GET.get("patient")} if request.GET.get("patient") else None
    form = AppointmentWizardForm(data, initial=initial)
    slots = []
    if request.method == "POST" and form.is_valid():
        slots = get_available_slots(form.cleaned_data["doctor"], form.cleaned_data["appointment_date"])
        if request.method == "POST" and request.POST.get("action") == "book":
            raw_slot = request.POST.get("slot", "")
            try:
                selected_time = time.fromisoformat(raw_slot)
                appointment = create_appointment(
                    patient=form.cleaned_data["patient"], doctor=form.cleaned_data["doctor"],
                    service=form.cleaned_data["service"], selected_date=form.cleaned_data["appointment_date"],
                    start_time=selected_time, user=request.user, comment=form.cleaned_data["comment"],
                    referral_info=form.cleaned_data["referral_info"],
                )
            except (ValueError, ValidationError) as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Пациент успешно записан на приём.")
                return redirect("scheduling:detail", pk=appointment.pk)
    return render(request, "scheduling/appointment_form.html", {"form": form, "slots": slots})


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("patient", "doctor", "planned_service", "created_by"), pk=pk)
    if request.user.role == User.Role.DOCTOR and appointment.doctor_id != request.user.id:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return render(request, "scheduling/appointment_detail.html", {"appointment": appointment})


@role_required(User.Role.ADMINISTRATOR)
def appointment_cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == "POST" and appointment.status == Appointment.Status.PLANNED:
        appointment.status = Appointment.Status.CANCELLED
        appointment.save(update_fields=("status", "updated_at"))
        messages.success(request, "Запись отменена. Интервал снова доступен.")
    return redirect("scheduling:detail", pk=pk)


@role_required(User.Role.ADMINISTRATOR)
def appointment_reschedule(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("doctor", "patient"), pk=pk)
    form = RescheduleForm(request.POST or request.GET or None, initial={"appointment_date": appointment.appointment_date})
    slots = []
    if form.is_valid():
        slots = get_available_slots(appointment.doctor, form.cleaned_data["appointment_date"], exclude_appointment=appointment)
        if request.method == "POST" and request.POST.get("action") == "move":
            try:
                selected_time = time.fromisoformat(request.POST.get("slot", ""))
                move_appointment(appointment, form.cleaned_data["appointment_date"], selected_time)
            except (ValueError, ValidationError) as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Запись перенесена. Старый интервал освобождён.")
                return redirect("scheduling:detail", pk=appointment.pk)
    return render(request, "scheduling/reschedule.html", {"form": form, "slots": slots, "appointment": appointment})


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def schedule_view(request):
    doctors = User.objects.filter(role=User.Role.DOCTOR, is_active=True).order_by("last_name")
    if request.user.role == User.Role.DOCTOR:
        doctors = doctors.filter(pk=request.user.pk)
    schedules = DoctorScheduleTemplate.objects.filter(doctor__in=doctors, is_active=True).select_related("doctor")
    return render(request, "scheduling/schedule.html", {"doctors": doctors, "schedules": schedules, "today": timezone.localdate()})
