from datetime import date, time

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Doctor, User
from accounts.permissions import role_required
from billing.models import Service
from .forms import AppointmentWizardForm, RescheduleForm
from .models import Appointment, DoctorScheduleTemplate
from .services import create_appointment, get_available_slots, move_appointment


def _parse_selected_time(raw_value):
    if not raw_value:
        raise ValidationError("Выберите доступное время приёма.")
    try:
        return time.fromisoformat(raw_value)
    except ValueError as error:
        raise ValidationError("Выбранное время имеет неверный формат. Обновите список интервалов.") from error


def _parse_selected_date(raw_value):
    try:
        selected_date = date.fromisoformat(raw_value or "")
    except ValueError as error:
        raise ValidationError("Выберите корректную дату приёма.") from error
    if selected_date < timezone.localdate():
        raise ValidationError("Нельзя выбрать прошедшую дату.")
    return selected_date


def _validation_message(error):
    return error.messages[0] if isinstance(error, ValidationError) and error.messages else str(error)


def _slots_json(slots, *, duration_minutes):
    serialized = [
        {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}
        for start, end in slots
    ]
    if serialized:
        message = f"Найдено интервалов: {len(serialized)}. Продолжительность приёма — {duration_minutes} мин."
    else:
        message = f"Свободных интервалов на выбранную дату нет. Продолжительность приёма — {duration_minutes} мин."
    return JsonResponse({"slots": serialized, "duration_minutes": duration_minutes, "message": message})


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR)
def appointment_list(request):
    appointments = Appointment.objects.select_related("patient", "doctor", "planned_service")
    if request.user.role == User.Role.DOCTOR:
        appointments = appointments.filter(doctor_id=request.user.pk)
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
        slots = get_available_slots(form.cleaned_data["doctor"], form.cleaned_data["appointment_date"], form.cleaned_data["service"])
        if request.method == "POST" and request.POST.get("action") == "book":
            try:
                selected_time = _parse_selected_time(request.POST.get("slot", ""))
                appointment = create_appointment(
                    patient=form.cleaned_data["patient"], doctor=form.cleaned_data["doctor"],
                    service=form.cleaned_data["service"], selected_date=form.cleaned_data["appointment_date"],
                    start_time=selected_time, user=request.user, comment=form.cleaned_data["comment"],
                    referral_info=form.cleaned_data["referral_info"],
                )
            except (ValueError, ValidationError) as error:
                form.add_error(None, error)
                slots = get_available_slots(
                    form.cleaned_data["doctor"], form.cleaned_data["appointment_date"], form.cleaned_data["service"]
                )
            else:
                messages.success(request, "Пациент успешно записан на приём.")
                return redirect("scheduling:detail", pk=appointment.pk)
    return render(request, "scheduling/appointment_form.html", {"form": form, "slots": slots})


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR)
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("patient", "doctor", "planned_service", "created_by"), pk=pk)
    if request.user.role == User.Role.DOCTOR and appointment.doctor_id != request.user.id:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return render(request, "scheduling/appointment_detail.html", {"appointment": appointment})


@role_required(User.Role.ADMINISTRATOR)
def appointment_cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method != "POST":
        messages.error(request, "Отмена записи выполняется только после подтверждения.")
    elif Appointment.objects.filter(pk=pk, status=Appointment.Status.PLANNED).update(
        status=Appointment.Status.CANCELLED,
        updated_at=timezone.now(),
    ):
        messages.success(request, "Запись отменена. Интервал снова доступен.")
    else:
        messages.error(request, "Запись уже изменила статус и не может быть отменена.")
    return redirect("scheduling:detail", pk=pk)


@role_required(User.Role.ADMINISTRATOR)
def appointment_reschedule(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("doctor", "patient", "planned_service"), pk=pk)
    if appointment.status != Appointment.Status.PLANNED:
        messages.error(request, "Перенести можно только запланированную запись.")
        return redirect("scheduling:detail", pk=appointment.pk)
    form = RescheduleForm(request.POST or request.GET or None, initial={"appointment_date": appointment.appointment_date})
    slots = []
    if form.is_valid():
        slots = get_available_slots(
            appointment.doctor,
            form.cleaned_data["appointment_date"],
            duration_minutes=appointment.duration_minutes,
            exclude_appointment=appointment,
        )
        if request.method == "POST" and request.POST.get("action") == "move":
            try:
                selected_time = _parse_selected_time(request.POST.get("slot", ""))
                move_appointment(appointment, form.cleaned_data["appointment_date"], selected_time)
            except (ValueError, ValidationError) as error:
                form.add_error(None, error)
                appointment.refresh_from_db()
                slots = get_available_slots(
                    appointment.doctor,
                    form.cleaned_data["appointment_date"],
                    duration_minutes=appointment.duration_minutes,
                    exclude_appointment=appointment,
                )
            else:
                messages.success(request, "Запись перенесена. Старый интервал освобождён.")
                return redirect("scheduling:detail", pk=appointment.pk)
    return render(request, "scheduling/reschedule.html", {"form": form, "slots": slots, "appointment": appointment})


@role_required(User.Role.ADMINISTRATOR)
def available_slots(request):
    try:
        selected_date = _parse_selected_date(request.GET.get("date"))
        doctor_id = int(request.GET.get("doctor", ""))
        service_id = int(request.GET.get("service", ""))
    except (TypeError, ValueError, ValidationError) as error:
        return JsonResponse({"slots": [], "message": _validation_message(error)}, status=400)

    doctor = Doctor.objects.filter(pk=doctor_id, user__role=User.Role.DOCTOR, user__is_active=True).first()
    service = Service.objects.filter(pk=service_id, is_active=True).first()
    if not doctor or not service:
        return JsonResponse({"slots": [], "message": "Врач или услуга недоступны. Обновите страницу."}, status=404)
    return _slots_json(
        get_available_slots(doctor, selected_date, service),
        duration_minutes=service.duration_minutes,
    )


@role_required(User.Role.ADMINISTRATOR)
def reschedule_available_slots(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("doctor"), pk=pk)
    if appointment.status != Appointment.Status.PLANNED:
        return JsonResponse({"slots": [], "message": "Перенести можно только запланированную запись."}, status=409)
    try:
        selected_date = _parse_selected_date(request.GET.get("date"))
    except ValidationError as error:
        return JsonResponse({"slots": [], "message": _validation_message(error)}, status=400)
    return _slots_json(
        get_available_slots(
            appointment.doctor,
            selected_date,
            duration_minutes=appointment.duration_minutes,
            exclude_appointment=appointment,
        ),
        duration_minutes=appointment.duration_minutes,
    )


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def schedule_view(request):
    doctors = Doctor.objects.filter(user__role=User.Role.DOCTOR, user__is_active=True).select_related("user").order_by("user__last_name")
    if request.user.role == User.Role.DOCTOR:
        doctors = doctors.filter(pk=request.user.pk)
    schedules = DoctorScheduleTemplate.objects.filter(doctor__in=doctors, is_active=True).select_related("doctor")
    return render(request, "scheduling/schedule.html", {"doctors": doctors, "schedules": schedules, "today": timezone.localdate()})
