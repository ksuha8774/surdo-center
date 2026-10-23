import uuid

from django.db import models
from django.db.models import Q


class ExternalSystem(models.Model):
    code = models.CharField("Код", max_length=50, unique=True)
    name = models.CharField("Название", max_length=120)
    is_active = models.BooleanField("Активна", default=True)

    def __str__(self):
        return self.name


class DoctorExternalMapping(models.Model):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT, related_name="doctor_mappings")
    doctor = models.ForeignKey("accounts.Doctor", on_delete=models.CASCADE, related_name="external_mappings")
    external_staff_id = models.CharField("ID сотрудника во внешней системе", max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("external_system", "doctor"), name="unique_external_doctor_mapping"),
            models.UniqueConstraint(fields=("external_system", "external_staff_id"), name="unique_external_staff_id"),
        ]


class ServiceExternalMapping(models.Model):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT, related_name="service_mappings")
    service = models.ForeignKey("billing.Service", on_delete=models.CASCADE, related_name="external_mappings")
    external_service_id = models.CharField("ID услуги во внешней системе", max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("external_system", "service"), name="unique_external_service_mapping"),
            models.UniqueConstraint(fields=("external_system", "external_service_id"), name="unique_external_service_id"),
        ]


class ExternalBookingRequest(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Получена"
        MATCHED = "matched", "Сопоставлена"
        REJECTED = "rejected", "Отклонена"

    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT, related_name="booking_requests")
    external_booking_id = models.CharField("ID внешней записи", max_length=120)
    client_name = models.CharField("Имя клиента", max_length=200)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    comment = models.TextField("Комментарий", blank=True)
    requested_service_external_id = models.CharField("Внешний ID услуги", max_length=120, blank=True)
    requested_staff_external_id = models.CharField("Внешний ID сотрудника", max_length=120, blank=True)
    appointment_date = models.DateField("Желаемая дата", null=True, blank=True)
    start_time = models.TimeField("Желаемое начало", null=True, blank=True)
    end_time = models.TimeField("Желаемое окончание", null=True, blank=True)
    patient = models.ForeignKey("patients.Patient", on_delete=models.SET_NULL, null=True, blank=True, related_name="external_booking_requests")
    appointment = models.OneToOneField("scheduling.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="external_request")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.RECEIVED)
    received_at = models.DateTimeField("Получена", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("external_system", "external_booking_id"), name="unique_external_booking_request"),
            models.CheckConstraint(
                condition=(
                    Q(start_time__isnull=True, end_time__isnull=True)
                    | Q(start_time__isnull=False, end_time__isnull=False, start_time__lt=models.F("end_time"))
                ),
                name="external_request_time_order",
            ),
        ]


class SyncEvent(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Входящее"
        OUTBOUND = "outbound", "Исходящее"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает обработки"
        COMPLETED = "completed", "Обработано"
        ERROR = "error", "Ошибка"

    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT, related_name="sync_events")
    idempotency_key = models.UUIDField("Ключ идемпотентности", default=uuid.uuid4, unique=True, editable=False)
    external_event_id = models.CharField("ID внешнего события", max_length=120, blank=True)
    external_object_id = models.CharField("ID внешнего объекта", max_length=120, blank=True)
    entity_type = models.CharField("Тип сущности", max_length=50)
    direction = models.CharField("Направление", max_length=10, choices=Direction.choices)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    payload_checksum = models.CharField("Контрольная сумма содержимого", max_length=64, blank=True)
    error_message = models.TextField("Ошибка", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    processed_at = models.DateTimeField("Обработано", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("external_system", "external_event_id"),
                condition=~Q(external_event_id=""),
                name="unique_external_sync_event",
            ),
        ]
