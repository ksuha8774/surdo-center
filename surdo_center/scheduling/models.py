from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import DateTimeField, ExpressionWrapper, F, Func, Q, Value


class DoctorScheduleTemplate(models.Model):
    WEEKDAYS = (
        (0, "Понедельник"), (1, "Вторник"), (2, "Среда"), (3, "Четверг"),
        (4, "Пятница"), (5, "Суббота"), (6, "Воскресенье"),
    )
    doctor = models.ForeignKey("accounts.Doctor", on_delete=models.PROTECT, related_name="schedule_templates")
    weekday = models.PositiveSmallIntegerField("День недели", choices=WEEKDAYS)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    booking_step_minutes = models.PositiveSmallIntegerField("Шаг начала записи, минут", default=15)
    valid_from = models.DateField("Действует с")
    valid_to = models.DateField("Действует по", null=True, blank=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ("doctor", "weekday", "start_time")
        constraints = [
            models.CheckConstraint(condition=Q(weekday__range=(0, 6)), name="schedule_weekday_0_6"),
            models.CheckConstraint(condition=Q(start_time__lt=F("end_time")), name="schedule_time_order"),
            models.CheckConstraint(condition=Q(booking_step_minutes__gt=0), name="schedule_booking_step_positive"),
            models.CheckConstraint(condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")), name="schedule_valid_dates_order"),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        if self.valid_to and self.valid_from > self.valid_to:
            raise ValidationError({"valid_to": "Дата окончания должна быть не раньше даты начала."})


class DoctorScheduleException(models.Model):
    doctor = models.ForeignKey("accounts.Doctor", on_delete=models.PROTECT, related_name="schedule_exceptions")
    exception_date = models.DateField("Дата")
    start_time = models.TimeField("Начало", null=True, blank=True)
    end_time = models.TimeField("Окончание", null=True, blank=True)
    is_day_off = models.BooleanField("Выходной", default=False)
    is_available = models.BooleanField("Дополнительное рабочее время", default=False)
    reason = models.CharField("Причина или комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ("doctor", "exception_date", "start_time")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(is_day_off=True, is_available=False, start_time__isnull=True, end_time__isnull=True)
                    | Q(is_day_off=False, start_time__isnull=False, end_time__isnull=False, start_time__lt=F("end_time"))
                ),
                name="schedule_exception_shape_valid",
            ),
            models.UniqueConstraint(fields=("doctor", "exception_date"), condition=Q(is_day_off=True), name="unique_doctor_day_off"),
            models.UniqueConstraint(
                fields=("doctor", "exception_date", "start_time", "end_time", "is_available"),
                condition=Q(is_day_off=False),
                name="unique_doctor_timed_exception",
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_day_off:
            if self.is_available or self.start_time or self.end_time:
                raise ValidationError("Для полного выходного время не указывается.")
        elif not self.start_time or not self.end_time:
            raise ValidationError("Для перерыва или дополнительного рабочего времени укажите начало и окончание.")
        elif self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})


class Appointment(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирована"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        NO_SHOW = "no_show", "Неявка"

    class BookingSource(models.TextChoices):
        INTERNAL = "internal", "АСУ"
        YCLIENTS = "yclients", "YCLIENTS"
        OTHER = "other", "Другая внешняя система"

    class SyncStatus(models.TextChoices):
        LOCAL = "local", "Только локально"
        PENDING = "pending", "Ожидает синхронизации"
        SYNCED = "synced", "Синхронизирована"
        ERROR = "error", "Ошибка синхронизации"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    doctor = models.ForeignKey("accounts.Doctor", on_delete=models.PROTECT, related_name="appointments")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_appointments", null=True, blank=True)
    planned_service = models.ForeignKey("billing.Service", on_delete=models.PROTECT, related_name="planned_appointments")
    appointment_date = models.DateField("Дата", db_index=True)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    planned_price = models.DecimalField("Плановая цена", max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True)
    booking_source = models.CharField("Источник записи", max_length=20, choices=BookingSource.choices, default=BookingSource.INTERNAL)
    external_system = models.ForeignKey(
        "integrations.ExternalSystem",
        on_delete=models.PROTECT,
        related_name="appointments",
        null=True,
        blank=True,
    )
    external_booking_id = models.CharField("ID записи во внешней системе", max_length=120, blank=True)
    sync_status = models.CharField("Состояние синхронизации", max_length=20, choices=SyncStatus.choices, default=SyncStatus.LOCAL)
    last_sync_error = models.TextField("Последняя ошибка синхронизации", blank=True)
    last_synced_at = models.DateTimeField("Последняя успешная синхронизация", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    referral_info = models.TextField("Сведения о направлении", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("appointment_date", "start_time")
        indexes = [models.Index(fields=("doctor", "appointment_date", "status"))]
        constraints = [
            models.CheckConstraint(condition=Q(start_time__lt=F("end_time")), name="appointment_time_order"),
            models.CheckConstraint(condition=Q(planned_price__isnull=True) | Q(planned_price__gte=0), name="appointment_planned_price_nonnegative"),
            models.CheckConstraint(
                condition=Q(status__in=("planned", "in_progress", "completed", "cancelled", "no_show")),
                name="appointment_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(booking_source__in=("internal", "yclients", "other")),
                name="appointment_booking_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(sync_status__in=("local", "pending", "synced", "error")),
                name="appointment_sync_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(external_system__isnull=True, external_booking_id="")
                    | (Q(external_system__isnull=False) & Q(external_booking_id__gt=""))
                ),
                name="appointment_external_identity_complete",
            ),
            models.UniqueConstraint(
                fields=("external_system", "external_booking_id"),
                condition=~Q(external_booking_id=""),
                name="unique_external_appointment",
            ),
            ExclusionConstraint(
                name="exclude_overlapping_doctor_appointments",
                expressions=(
                    ("doctor", RangeOperators.EQUAL),
                    (
                        Func(
                            ExpressionWrapper(F("appointment_date") + F("start_time"), output_field=DateTimeField()),
                            ExpressionWrapper(F("appointment_date") + F("end_time"), output_field=DateTimeField()),
                            Value("[)"),
                            function="TSRANGE",
                            output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ),
                condition=~Q(status="cancelled"),
            ),
        ]

    @property
    def duration_minutes(self):
        if not self.appointment_date or not self.start_time or not self.end_time:
            return None
        from datetime import datetime
        start = datetime.combine(self.appointment_date, self.start_time)
        end = datetime.combine(self.appointment_date, self.end_time)
        return int((end - start).total_seconds() // 60)

    def clean(self):
        super().clean()
        if self.patient_id and self.patient.is_archived:
            raise ValidationError({"patient": "Архивного пациента нельзя записать на новый приём."})
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        if bool(self.external_system_id) != bool(self.external_booking_id):
            raise ValidationError("Внешняя система и внешний ID должны быть заполнены вместе.")

    def save(self, *args, **kwargs):
        if self._state.adding and self.patient_id:
            from patients.models import Patient

            with transaction.atomic():
                patient = Patient.objects.select_for_update().get(pk=self.patient_id)
                if patient.is_archived:
                    raise ValidationError({
                        "patient": "Архивного пациента нельзя записать на новый приём. "
                        "Сначала восстановите его карточку."
                    })
                self.patient = patient
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.appointment_date:%d.%m.%Y} {self.start_time:%H:%M} — {self.patient}"
