from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class RoleInterfaceSmokeTests(TestCase):
    def test_each_role_dashboard_renders(self):
        for role in (User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR):
            user = User.objects.create_user(username=f"user-{role}", password="pass12345", role=role)
            self.client.force_login(user)
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, user.get_role_display())

    def test_administrator_can_open_booking_wizard(self):
        user = User.objects.create_user(username="admin", password="pass12345", role=User.Role.ADMINISTRATOR)
        self.client.force_login(user)
        response = self.client.get(reverse("scheduling:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Записать пациента на приём")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
