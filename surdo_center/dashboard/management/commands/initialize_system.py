from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import Service


class Command(BaseCommand):
    help = "Создаёт обязательные начальные справочники системы"

    def handle(self, *args, **options):
        services = (
            ("Первичный приём врача-сурдолога", Decimal("2500.00")),
            ("Повторный приём врача-сурдолога", Decimal("1800.00")),
            ("Консультация по результатам обследования", Decimal("1500.00")),
        )
        for name, price in services:
            Service.objects.get_or_create(name=name, defaults={"price": price, "is_active": True})

        self.stdout.write(self.style.SUCCESS("Начальные справочники системы подготовлены."))
