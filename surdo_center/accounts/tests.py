from django.test import TestCase
from django.urls import reverse

from .models import User


class RoleAccessTests(TestCase):
    def test_doctor_cannot_open_patient_creation(self):
        doctor = User.objects.create_user(username="doctor", password="pass12345", role=User.Role.DOCTOR)
        self.client.force_login(doctor)
        self.assertEqual(self.client.get(reverse("patients:create")).status_code, 403)


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="administrator",
            password="pass12345",
            role=User.Role.ADMINISTRATOR,
        )

    def test_login_page_contains_new_branding(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Вход в систему")
        self.assertContains(response, "images/surdo-center-logo.png")

    def test_session_ends_with_browser_without_remember_me(self):
        self.client.post(reverse("login"), {"username": "administrator", "password": "pass12345"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_keeps_session_for_fourteen_days(self):
        self.client.post(
            reverse("login"),
            {"username": "administrator", "password": "pass12345", "remember_me": "1"},
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreaterEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 13)
