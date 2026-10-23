from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DoctorScheduleTemplate(models.Model):
    WEEKDAYS = (
        (0, "Понедельник"), (1, "Вторник"), (2, "Среда"), (3, "Четверг"),
        (4, "Пятница"), (5, "Суббота"), (6, "Воскресенье"),
    )
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="schedule_templates")
    weekday = models.PositiveSmallIntegerField("День недели", choices=WEEKDAYS)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    slot_duration_min = models.PositiveSmallIntegerField("Длительность приёма, минут", default=30)
    valid_from = models.DateField("Действует с")
    valid_to = models.DateField("Действует по", null=True, blank=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ("doctor", "weekday", "start_time")

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        if self.valid_to and self.valid_from > self.valid_to:
            raise ValidationError({"valid_to": "Дата окончания должна быть не раньше даты начала."})
        if self.doctor_id and self.doctor.role != "doctor":
            raise ValidationError({"doctor": "Рабочий график можно назначить только врачу."})


class DoctorScheduleException(models.Model):
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="schedule_exceptions")
    date = models.DateField("Дата")
    start_time = models.TimeField("Начало", null=True, blank=True)
    end_time = models.TimeField("Окончание", null=True, blank=True)
    is_day_off = models.BooleanField("Выходной", default=True)
    reason = models.CharField("Причина или комментарий", max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("doctor", "date"), name="unique_doctor_schedule_exception")]

    def clean(self):
        if not self.is_day_off and (not self.start_time or not self.end_time):
            raise ValidationError("Для изменённого рабочего дня укажите начало и окончание.")
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})


class Appointment(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирована"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        NO_SHOW = "no_show", "Неявка"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="doctor_appointments")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_appointments")
    planned_service = models.ForeignKey("billing.Service", on_delete=models.PROTECT, related_name="planned_appointments")
    appointment_date = models.DateField("Дата", db_index=True)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True)
    comment = models.TextField("Комментарий", blank=True)
    referral_info = models.TextField("Сведения о направлении", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("appointment_date", "start_time")
        indexes = [models.Index(fields=("doctor", "appointment_date", "status"))]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        if self.doctor_id and self.doctor.role != "doctor":
            raise ValidationError({"doctor": "Для записи необходимо выбрать врача-сурдолога."})

    def __str__(self):
        return f"{self.appointment_date:%d.%m.%Y} {self.start_time:%H:%M} — {self.patient}"
