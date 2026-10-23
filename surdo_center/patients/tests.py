from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .forms import PatientForm
from .models import Patient


class PatientFormTests(TestCase):
    def test_phone_is_normalized(self):
        form = PatientForm(data={
            "last_name": "Иванов", "first_name": "Иван", "middle_name": "", "birth_date": "1990-01-01",
            "sex": "male", "phone": "8 (900) 111-22-33", "email": "", "city": "Иркутск",
            "street": "Ленина", "house": "1", "apartment": "", "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+79001112233")

    def test_patient_is_created_with_audit_timestamps(self):
        patient = Patient.objects.create(
            last_name="Иванова", first_name="Анна", birth_date="1995-05-10", sex="female",
            phone="+79001112234", city="Иркутск", street="Ленина", house="2",
        )
        self.assertIsNotNone(patient.created_at)
        self.assertIsNotNone(patient.updated_at)

    def test_future_birth_date_is_rejected(self):
        patient = Patient(
            last_name="Будущая", first_name="Дата", birth_date=timezone.localdate() + timedelta(days=1),
            sex="female", phone="+79001112235", city="Иркутск", street="Ленина", house="3",
        )
        with self.assertRaises(ValidationError):
            patient.full_clean()
