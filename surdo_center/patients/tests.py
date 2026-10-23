from django.test import TestCase

from .forms import PatientForm


class PatientFormTests(TestCase):
    def test_phone_is_normalized(self):
        form = PatientForm(data={
            "last_name": "Иванов", "first_name": "Иван", "middle_name": "", "birth_date": "1990-01-01",
            "sex": "male", "phone": "8 (900) 111-22-33", "email": "", "city": "Иркутск",
            "street": "Ленина", "house": "1", "apartment": "", "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+79001112233")
