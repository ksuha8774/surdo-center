from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Service(models.Model):
    name = models.CharField("Название", max_length=150, unique=True)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class ProvidedService(models.Model):
    visit = models.ForeignKey("medical.MedicalVisit", on_delete=models.PROTECT, related_name="provided_services")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="provided_items")
    quantity = models.PositiveIntegerField("Количество", default=1)
    price_at_time = models.DecimalField("Цена на момент оказания", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    @property
    def total_amount(self):
        return self.quantity * self.price_at_time


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        CARD = "card", "Банковская карта"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        PAID = "paid", "Оплачено"
        CANCELLED = "cancelled", "Отменено"

    visit = models.ForeignKey("medical.MedicalVisit", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_at = models.DateTimeField("Дата и время оплаты")
    method = models.CharField("Способ", max_length=20, choices=Method.choices)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PAID)
