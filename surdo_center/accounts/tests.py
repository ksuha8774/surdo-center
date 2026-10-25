from django.test import TestCase
from django.urls import reverse

from django.core.exceptions import ValidationError
from .models import Doctor, User
from unittest.mock import patch


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
        self.assertContains(response, "Медицинский центр «ЮНА»")
        self.assertContains(response, "images/yuna-logo.png")

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


class DoctorModelTests(TestCase):

    def test_director_cannot_have_doctor_profile(self):
        director = User.objects.create_user(
            username="test_director",
            password="test12345",
            role=User.Role.DIRECTOR,
        )

        with self.assertRaises(ValidationError):
            Doctor.objects.create(
                user=director,
                specialization="Сурдолог",
            )

    def test_doctor_cannot_change_role_with_profile(self):
        doctor_user = User.objects.create_user(
            username="test_doctor",
            password="test12345",
            role=User.Role.DOCTOR,
        )

        Doctor.objects.create(
            user=doctor_user,
            specialization="Сурдолог",
        )

        doctor_user.role = User.Role.DIRECTOR

        with self.assertRaises(ValidationError):
            doctor_user.save()

class EmployeeAdminTests(TestCase):

    def test_creating_doctor_creates_profile(self):
        superadmin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        self.client.force_login(superadmin)

        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "new_doctor",
                "usable_password": "true",
                "password1": "StrongTestPass_926!",
                "password2": "StrongTestPass_926!",
                "first_name": "Иван",
                "last_name": "Иванов",
                "middle_name": "Иванович",
                "role": User.Role.DOCTOR,
                "specialization": "Сурдолог",
                "_save": "Сохранить",
            },
        )

        self.assertEqual(response.status_code, 302)

        doctor_user = User.objects.get(
            username="new_doctor"
        )

        self.assertEqual(
            doctor_user.doctor_profile.specialization,
            "Сурдолог",
        )

    def test_creating_registrar_without_doctor_profile(self):
        superadmin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        self.client.force_login(superadmin)

        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "new_registrar",
                "usable_password": "true",
                "password1": "StrongTestPass_926!",
                "password2": "StrongTestPass_926!",
                "first_name": "Анна",
                "last_name": "Петрова",
                "middle_name": "Ивановна",
                "role": User.Role.ADMINISTRATOR,
                "_save": "Сохранить",
            },
        )

        self.assertEqual(response.status_code, 302)

        registrar = User.objects.get(
            username="new_registrar"
        )

        self.assertFalse(
            Doctor.objects.filter(user=registrar).exists()
        )
    def test_doctor_creation_is_atomic(self):
        superadmin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        self.client.force_login(superadmin)

        with patch(
            "accounts.admin.Doctor.objects.create",
            side_effect=RuntimeError("Ошибка создания профиля"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("admin:accounts_user_add"),
                    {
                        "username": "atomic_doctor",
                        "usable_password": "true",
                        "password1": "StrongTestPass_926!",
                        "password2": "StrongTestPass_926!",
                        "first_name": "Иван",
                        "last_name": "Иванов",
                        "middle_name": "Иванович",
                        "role": User.Role.DOCTOR,
                        "specialization": "Сурдолог",
                        "_save": "Сохранить",
                    },
                )

        self.assertFalse(
            User.objects.filter(
                username="atomic_doctor"
            ).exists()
        )

    def test_registrar_cannot_have_specialization(self):
        superadmin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        self.client.force_login(superadmin)

        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "registrar_invalid",
                "usable_password": "true",
                "password1": "StrongTestPass_926!",
                "password2": "StrongTestPass_926!",
                "role": User.Role.ADMINISTRATOR,
                "specialization": "Сурдолог",
                "_save": "Сохранить",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Специализацию можно указывать только для врача."
        )

        self.assertFalse(
            User.objects.filter(
                username="registrar_invalid"
            ).exists()
        )


class DoctorAdminTests(TestCase):

    def test_cannot_change_doctor_user(self):
        admin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        doctor_user = User.objects.create_user(
            username="test_doctor",
            password="StrongTestPass_926!",
            role=User.Role.DOCTOR,
        )

        another_user = User.objects.create_user(
            username="another_doctor",
            password="StrongTestPass_926!",
            role=User.Role.DOCTOR,
        )

        Doctor.objects.create(
            user=doctor_user,
            specialization="Сурдолог",
        )

        self.client.force_login(admin)

        response = self.client.post(
            reverse(
                "admin:accounts_doctor_change",
                args=[doctor_user.pk],
            ),
            {
                "user": another_user.pk,
                "specialization": "Аудиолог",
                "_save": "Сохранить",
            },
        )

        self.assertEqual(response.status_code, 302)

        profile = Doctor.objects.get(user=doctor_user)

        self.assertEqual(profile.user_id, doctor_user.pk)
        self.assertEqual(profile.specialization, "Аудиолог")

        self.assertFalse(
            Doctor.objects.filter(user=another_user).exists()
        )

class DoctorDeactivationTests(TestCase):

    def test_deactivation_preserves_profile(self):
        doctor_user = User.objects.create_user(
            username="inactive_doctor",
            password="StrongTestPass_926!",
            role=User.Role.DOCTOR,
        )

        doctor = Doctor.objects.create(
            user=doctor_user,
            specialization="Сурдолог",
        )

        # До деактивации врач может войти
        self.assertTrue(
            self.client.login(
                username="inactive_doctor",
                password="StrongTestPass_926!",
            )
        )

        self.client.logout()

        # Деактивируем учётную запись
        doctor_user.is_active = False
        doctor_user.save(update_fields=["is_active"])

        # Проверяем, что вход запрещён
        self.assertFalse(
            self.client.login(
                username="inactive_doctor",
                password="StrongTestPass_926!",
            )
        )

        # Проверяем, что профиль врача сохранился
        self.assertTrue(
            Doctor.objects.filter(pk=doctor.pk).exists()
        )

class AccountDeletionAdminTests(TestCase):

    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="test_superadmin",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_login(self.superadmin)

    def test_user_deletion_forbidden(self):
        user = User.objects.create_user(
            username="test_registrar",
            password="StrongTestPass_926!",
            role=User.Role.ADMINISTRATOR,
        )

        response = self.client.get(
            reverse(
                "admin:accounts_user_delete",
                args=[user.pk],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_doctor_deletion_forbidden(self):
        user = User.objects.create_user(
            username="test_doctor",
            password="StrongTestPass_926!",
            role=User.Role.DOCTOR,
        )

        doctor = Doctor.objects.create(
            user=user,
            specialization="Сурдолог",
        )

        response = self.client.get(
            reverse(
                "admin:accounts_doctor_delete",
                args=[doctor.pk],
            )
        )

        self.assertEqual(response.status_code, 403)