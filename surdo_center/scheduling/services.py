from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from accounts.models import User
from .models import Appointment, DoctorScheduleException, DoctorScheduleTemplate


def _overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def get_available_slots(doctor, selected_date, exclude_appointment=None):
    if not doctor or doctor.role != User.Role.DOCTOR or selected_date < timezone.localdate():
        return []

    templates = list(DoctorScheduleTemplate.objects.filter(
        doctor=doctor,
        weekday=selected_date.weekday(),
        valid_from__lte=selected_date,
        is_active=True,
    ).filter(models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=selected_date)))
    if not templates:
        return []

    exception = DoctorScheduleException.objects.filter(doctor=doctor, date=selected_date).first()
    if exception and exception.is_day_off:
        return []

    if exception:
        duration = min(item.slot_duration_min for item in templates)
        intervals = [(exception.start_time, exception.end_time, duration)]
    else:
        intervals = [(item.start_time, item.end_time, item.slot_duration_min) for item in templates]

    busy = Appointment.objects.filter(doctor=doctor, appointment_date=selected_date).exclude(status=Appointment.Status.CANCELLED)
    if exclude_appointment:
        busy = busy.exclude(pk=exclude_appointment.pk)
    busy_intervals = list(busy.values_list("start_time", "end_time"))

    result = []
    now = timezone.localtime()
    for start, end, duration in intervals:
        cursor = datetime.combine(selected_date, start)
        interval_end = datetime.combine(selected_date, end)
        while cursor + timedelta(minutes=duration) <= interval_end:
            slot_end = cursor + timedelta(minutes=duration)
            is_past = selected_date == now.date() and cursor.time() <= now.time()
            occupied = any(_overlaps(cursor.time(), slot_end.time(), item_start, item_end) for item_start, item_end in busy_intervals)
            if not is_past and not occupied:
                result.append((cursor.time(), slot_end.time()))
            cursor = slot_end
    return sorted(set(result))


@transaction.atomic
def create_appointment(*, patient, doctor, service, selected_date, start_time, user, comment="", referral_info=""):
    doctor = User.objects.select_for_update().get(pk=doctor.pk)
    slots = get_available_slots(doctor, selected_date)
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
        comment=comment,
        referral_info=referral_info,
    )
    appointment.full_clean()
    appointment.save()
    return appointment


@transaction.atomic
def move_appointment(appointment, selected_date, start_time):
    locked = Appointment.objects.select_for_update().select_related("doctor").get(pk=appointment.pk)
    if locked.status != Appointment.Status.PLANNED:
        raise ValidationError("Перенести можно только запланированную запись.")
    User.objects.select_for_update().get(pk=locked.doctor_id)
    slots = get_available_slots(locked.doctor, selected_date, exclude_appointment=locked)
    match = next((item for item in slots if item[0] == start_time), None)
    if not match:
        raise ValidationError("Выбранный интервал уже занят или недоступен.")
    locked.appointment_date = selected_date
    locked.start_time, locked.end_time = match
    locked.full_clean()
    locked.save(update_fields=("appointment_date", "start_time", "end_time", "updated_at"))
    return locked
