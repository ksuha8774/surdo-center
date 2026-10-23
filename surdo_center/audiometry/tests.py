from datetime import time, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Doctor, User
from billing.models import Service
from medical.models import MedicalVisit
from patients.models import Patient
from scheduling.models import Appointment
from .models import AudiometryExam, AudiometryMeasurement


class AudiometryModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="audio-doctor", password="pass12345", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=user)
        patient = Patient.objects.create(
            last_name="Сидорова", first_name="Анна", birth_date="1992-01-01", sex="female",
            phone="+79000000002", city="Иркутск", street="Советская", house="3",
        )
        service = Service.objects.create(service_name="Аудиометрия", price=1000, duration_minutes=45)
        appointment = Appointment.objects.create(
            patient=patient, doctor=self.doctor, planned_service=service, planned_price=service.price,
            appointment_date=timezone.localdate() + timedelta(days=1), start_time=time(9), end_time=time(9, 45),
        )
        visit = MedicalVisit.objects.create(appointment=appointment)
        self.exam = AudiometryExam.objects.create(visit=visit, performed_by=self.doctor)

    def test_measurement_identity_includes_masking(self):
        values = {
            "exam": self.exam, "ear": "left", "conduction_type": "air", "frequency_hz": 1000,
            "threshold_db_hl": 25, "masked": False,
        }
        AudiometryMeasurement.objects.create(**values)
        AudiometryMeasurement.objects.create(**{**values, "masked": True})
        with self.assertRaises(IntegrityError), transaction.atomic():
            AudiometryMeasurement.objects.create(**values)

    def test_no_response_requires_recorded_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AudiometryMeasurement.objects.create(
                exam=self.exam, ear="right", conduction_type="bone", frequency_hz=2000,
                no_response=True, threshold_db_hl=80,
            )
