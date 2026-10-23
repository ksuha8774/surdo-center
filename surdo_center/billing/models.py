from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Service(models.Model):
    service_name = models.CharField("Название", max_length=150, unique=True)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    duration_minutes = models.PositiveSmallIntegerField(
        "Продолжительность, минут",
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ("service_name",)
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="service_price_nonnegative"),
            models.CheckConstraint(condition=models.Q(duration_minutes__gt=0), name="service_duration_positive"),
        ]

    def __str__(self):
        return self.service_name


class ProvidedService(models.Model):
    visit = models.ForeignKey("medical.MedicalVisit", on_delete=models.PROTECT, related_name="provided_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="provided_items")
    quantity = models.PositiveIntegerField("Количество", default=1)
    price_at_time = models.DecimalField("Цена на момент оказания", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="provided_service_quantity_positive"),
            models.CheckConstraint(condition=models.Q(price_at_time__gte=0), name="provided_service_price_nonnegative"),
        ]

    @property
    def total_amount(self):
        return self.quantity * self.price_at_time


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        CARD = "card", "Банковская карта"
        TRANSFER = "transfer", "Банковский перевод"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        COMPLETED = "completed", "Оплачено"
        CANCELLED = "cancelled", "Отменено"

    visit = models.ForeignKey("medical.MedicalVisit", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_at = models.DateTimeField("Дата и время оплаты", null=True, blank=True)
    payment_method = models.CharField("Способ", max_length=20, choices=Method.choices)
    payment_status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(
                condition=(
                    models.Q(payment_status="completed", paid_at__isnull=False)
                    | models.Q(payment_status="pending", paid_at__isnull=True)
                    | models.Q(payment_status="cancelled")
                ),
                name="payment_status_paid_at_consistent",
            ),
            models.CheckConstraint(
                condition=models.Q(payment_method__in=("cash", "card", "transfer", "other")),
                name="payment_method_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(payment_status__in=("pending", "completed", "cancelled")),
                name="payment_status_valid",
            ),
        ]
