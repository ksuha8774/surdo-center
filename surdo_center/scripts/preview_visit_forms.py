"""Create isolated synthetic fixtures for visual QA; never writes to the working database."""
import os
import sys
from datetime import date, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.core.management import call_command
from accounts.models import Doctor, User
from billing.models import Service
from medical.models import MedicalVisit
from patients.models import Patient
from scheduling.models import Appointment

if not settings.DATABASES["default"]["NAME"].startswith("yuna_forms_qa_"):
    raise SystemExit("Use only an isolated yuna_forms_qa_* database.")

call_command("migrate", interactive=False, verbosity=0)
user, _ = User.objects.get_or_create(username="doctor1", defaults={
    "role": "doctor", "last_name": "Тестовая", "first_name": "Мария",
})
user.set_password("12345")
user.save()
doctor, _ = Doctor.objects.get_or_create(user=user)
patient, _ = Patient.objects.get_or_create(last_name="Тестовый", first_name="Пациент", defaults={
    "birth_date": date(1990, 1, 1), "sex": "male", "phone": "+79000009999",
})
for index, (name, code) in enumerate([
    ("Первичный приём врача-сурдолога", "primary"),
    ("Повторный приём врача-сурдолога", "repeat"),
    ("Диагностика слуха", "hearing_diagnostic"),
    ("Консультация по результатам обследования", "results"),
    ("Краткая консультация", "brief"),
    ("Расширенный приём", "extended"),
], 1):
    service, _ = Service.objects.get_or_create(service_name=name, defaults={
        "price": 1000, "duration_minutes": 30, "medical_form_type": code,
    })
    appointment, _ = Appointment.objects.get_or_create(
        patient=patient, doctor=doctor, planned_service=service,
        appointment_date=date(2026, 12, 1) + timedelta(days=index),
        defaults={"start_time": time(10), "end_time": time(10, 30), "status": "in_progress"},
    )
    MedicalVisit.objects.get_or_create(appointment=appointment)
    print(code, f"http://127.0.0.1:8011/visits/appointment/{appointment.pk}/")
