from datetime import time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Doctor, User
from medical.models import MedicalVisit
from patients.models import Patient
from scheduling.models import Appointment
from .models import Payment, ProvidedService, Service


class BillingModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="billing-doctor", password="pass12345", role=User.Role.DOCTOR)
        doctor = Doctor.objects.create(user=user)
        patient = Patient.objects.create(
            last_name="Орлова", first_name="Елена", birth_date="1988-01-01", sex="female",
            phone="+79000000004", city="Иркутск", street="Байкальская", house="4",
        )
        self.service = Service.objects.create(
            service_name="Проверка слуха", price=Decimal("1200.00"), duration_minutes=45,
        )
        appointment = Appointment.objects.create(
            patient=patient, doctor=doctor, planned_service=self.service, planned_price=self.service.price,
            appointment_date=timezone.localdate() + timedelta(days=2), start_time=time(10), end_time=time(10, 45),
        )
        self.visit = MedicalVisit.objects.create(appointment=appointment)

    def test_service_requires_positive_duration(self):
        service = Service(service_name="Некорректная услуга", price=0, duration_minutes=0)
        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_provided_service_requires_positive_quantity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProvidedService.objects.create(
                visit=self.visit, service=self.service, quantity=0, price_at_time=self.service.price,
            )

    def test_completed_payment_requires_paid_at(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                visit=self.visit, amount=1000, payment_method=Payment.Method.CARD,
                payment_status=Payment.Status.COMPLETED,
            )
