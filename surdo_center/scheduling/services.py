from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from accounts.models import Doctor, User
from patients.models import Patient
from .models import Appointment, DoctorScheduleException, DoctorScheduleTemplate


def _overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def get_available_slots(doctor, selected_date, service=None, *, duration_minutes=None, exclude_appointment=None):
    if not doctor or selected_date < timezone.localdate():
        return []

    if (
        not doctor.user.is_active
        or doctor.user.role != User.Role.DOCTOR
    ):
        return []

    duration_minutes = duration_minutes or getattr(service, "duration_minutes", None)
    if not duration_minutes or duration_minutes <= 0:
        return []

    templates = list(DoctorScheduleTemplate.objects.filter(
        doctor=doctor,
        weekday=selected_date.weekday(),
        valid_from__lte=selected_date,
        is_active=True,
    ).filter(models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=selected_date)))
    exceptions = list(DoctorScheduleException.objects.filter(doctor=doctor, exception_date=selected_date))
    if any(item.is_day_off for item in exceptions):
        return []

    intervals = [(item.start_time, item.end_time, item.booking_step_minutes) for item in templates]
    default_step = min((item.booking_step_minutes for item in templates), default=15)
    intervals.extend(
        (item.start_time, item.end_time, default_step)
        for item in exceptions
        if item.is_available and not item.is_day_off
    )
    if not intervals:
        return []

    blocked_intervals = [
        (item.start_time, item.end_time)
        for item in exceptions
        if not item.is_available and not item.is_day_off
    ]

    busy = Appointment.objects.filter(doctor=doctor, appointment_date=selected_date).exclude(status=Appointment.Status.CANCELLED)
    if exclude_appointment:
        busy = busy.exclude(pk=exclude_appointment.pk)
    busy_intervals = list(busy.values_list("start_time", "end_time"))

    result = []
    now = timezone.localtime()
    for start, end, booking_step in intervals:
        cursor = datetime.combine(selected_date, start)
        interval_end = datetime.combine(selected_date, end)
        while cursor + timedelta(minutes=duration_minutes) <= interval_end:
            slot_end = cursor + timedelta(minutes=duration_minutes)
            is_past = selected_date == now.date() and cursor.time() <= now.time()
            occupied = any(_overlaps(cursor.time(), slot_end.time(), item_start, item_end) for item_start, item_end in busy_intervals)
            blocked = any(_overlaps(cursor.time(), slot_end.time(), item_start, item_end) for item_start, item_end in blocked_intervals)
            if not is_past and not occupied and not blocked:
                result.append((cursor.time(), slot_end.time()))
            cursor += timedelta(minutes=booking_step)
    return sorted(set(result))


@transaction.atomic
def create_appointment(*, patient, doctor, service, selected_date, start_time, user, comment="", referral_info=""):
    patient = Patient.objects.select_for_update().get(pk=patient.pk)
    if patient.is_archived:
        raise ValidationError("Архивного пациента нельзя записать на новый приём. Сначала восстановите его карточку.")
    doctor = Doctor.objects.select_for_update().get(pk=doctor.pk)
    slots = get_available_slots(doctor, selected_date, service)
    match = next((item for item in slots if item[0] == start_time), None)
    if not match:
        raise ValidationError("Выбранный интервал уже занят или недоступен. Обновите список времени.")
    appointment = Appointment(
        patient=patient,
        doctor=doctor,
        created_by=user,
        planned_service=service,
        appointment_date=selected_date,
        start_time=match[0],
        end_time=match[1],
        planned_price=service.price,
        comment=comment,
        referral_info=referral_info,
    )
    appointment.full_clean()
    try:
        with transaction.atomic():
            appointment.save()
    except IntegrityError as error:
        raise ValidationError("Интервал пересекается с другой действующей записью.") from error
    return appointment


@transaction.atomic
def move_appointment(appointment, selected_date, start_time):
    locked = Appointment.objects.select_for_update().select_related("doctor").get(pk=appointment.pk)
    if locked.status != Appointment.Status.PLANNED:
        raise ValidationError("Перенести можно только запланированную запись.")
    Doctor.objects.select_for_update().get(pk=locked.doctor_id)
    slots = get_available_slots(
        locked.doctor,
        selected_date,
        duration_minutes=locked.duration_minutes,
        exclude_appointment=locked,
    )
    match = next((item for item in slots if item[0] == start_time), None)
    if not match:
        raise ValidationError("Выбранный интервал уже занят или недоступен.")
    locked.appointment_date = selected_date
    locked.start_time, locked.end_time = match
    locked.full_clean()
    try:
        with transaction.atomic():
            locked.save(update_fields=("appointment_date", "start_time", "end_time", "updated_at"))
    except IntegrityError as error:
        raise ValidationError("Интервал пересекается с другой действующей записью.") from error
    return locked
