from datetime import time, timedelta
from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Doctor, User
from audiometry.models import AudiometryExam
from billing.models import Payment, ProvidedService, Service
from medical.models import MedicalVisit
from scheduling.models import Appointment

from .admin import PatientAdmin
from .forms import PatientForm
from .models import Patient
from .services import archive_patient, restore_patient


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

    def test_archived_patient_is_still_detected_as_exact_duplicate(self):
        existing = Patient.objects.create(
            last_name="Иванов", first_name="Иван", middle_name="Иванович",
            birth_date="1990-01-01", sex="male", phone="+79001112233",
            city="Иркутск", street="Ленина", house="1", is_archived=True,
        )
        form = PatientForm(data={
            "last_name": "Иванов", "first_name": "Иван", "middle_name": "Иванович",
            "birth_date": "1990-01-01", "sex": "male", "phone": "8 (900) 111-22-33",
            "email": "", "city": "Иркутск", "street": "Ленина", "house": "1",
            "apartment": "", "note": "",
        })
        self.assertFalse(form.is_valid())
        self.assertEqual(form.exact_duplicate, existing)


class PatientArchivingTests(TestCase):
    def setUp(self):
        self.registrar = User.objects.create_user(
            username="registrar", password="pass12345", role=User.Role.ADMINISTRATOR,
        )
        self.doctor_user = User.objects.create_user(
            username="doctor-archive", password="pass12345", role=User.Role.DOCTOR,
        )
        self.doctor = Doctor.objects.create(user=self.doctor_user)
        self.director = User.objects.create_user(
            username="director-archive", password="pass12345", role=User.Role.DIRECTOR,
        )
        self.patient = Patient.objects.create(
            last_name="Петров", first_name="Пётр", birth_date="1988-02-03", sex="male",
            phone="+79002223344", city="Иркутск", street="Мира", house="2",
        )
        self.service = Service.objects.create(
            service_name="Архивный тест", price=Decimal("1500.00"), duration_minutes=30,
        )

    def _appointment(self, *, status):
        return Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            created_by=self.registrar,
            planned_service=self.service,
            planned_price=self.service.price,
            appointment_date=timezone.localdate(),
            start_time=time(9),
            end_time=time(9, 30),
            status=status,
        )

    def test_archive_and_restore_are_idempotent(self):
        archived, changed = archive_patient(
            patient=self.patient, actor=self.registrar, reason="Карточка закрыта по заявлению",
        )
        self.assertTrue(changed)
        self.assertTrue(archived.is_archived)
        self.assertEqual(archived.archived_by, self.registrar)
        self.assertIsNotNone(archived.archived_at)

        archived_again, changed_again = archive_patient(patient=archived, actor=self.registrar)
        self.assertFalse(changed_again)
        self.assertEqual(archived_again.archived_at, archived.archived_at)

        restored, restored_changed = restore_patient(patient=archived, actor=self.registrar)
        self.assertTrue(restored_changed)
        self.assertFalse(restored.is_archived)
        self.assertIsNone(restored.archived_at)
        self.assertIsNone(restored.archived_by)
        self.assertEqual(restored.archive_reason, "")
        self.assertFalse(restore_patient(patient=restored, actor=self.registrar)[1])

    def test_unfinished_appointment_blocks_archiving_without_cancelling_it(self):
        appointment = self._appointment(status=Appointment.Status.IN_PROGRESS)
        with self.assertRaisesMessage(ValidationError, "есть незавершённая запись"):
            archive_patient(patient=self.patient, actor=self.registrar)
        self.patient.refresh_from_db()
        appointment.refresh_from_db()
        self.assertFalse(self.patient.is_archived)
        self.assertEqual(appointment.status, Appointment.Status.IN_PROGRESS)

    def test_related_medical_and_billing_data_survive_archiving(self):
        appointment = self._appointment(status=Appointment.Status.COMPLETED)
        visit = MedicalVisit.objects.create(appointment=appointment, conclusion="Слух сохранён")
        exam = AudiometryExam.objects.create(visit=visit, performed_by=self.doctor)
        provided = ProvidedService.objects.create(
            visit=visit, service=self.service, quantity=1, price_at_time=self.service.price,
        )
        payment = Payment.objects.create(
            visit=visit,
            amount=self.service.price,
            paid_at=timezone.now(),
            payment_method=Payment.Method.CARD,
            payment_status=Payment.Status.COMPLETED,
        )

        archive_patient(patient=self.patient, actor=self.registrar)

        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.assertTrue(MedicalVisit.objects.filter(pk=visit.pk).exists())
        self.assertTrue(AudiometryExam.objects.filter(pk=exam.pk).exists())
        self.assertTrue(ProvidedService.objects.filter(pk=provided.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_only_registrar_and_technical_admin_can_change_archive_status(self):
        with self.assertRaises(PermissionDenied):
            archive_patient(patient=self.patient, actor=self.doctor_user)
        with self.assertRaises(PermissionDenied):
            archive_patient(patient=self.patient, actor=self.director)

        technical_admin = User.objects.create_superuser(
            username="technical-admin", password="pass12345", role=User.Role.ADMINISTRATOR,
        )
        self.assertTrue(archive_patient(patient=self.patient, actor=technical_admin)[1])
        self.assertTrue(restore_patient(patient=self.patient, actor=technical_admin)[1])

        for user in (self.doctor_user, self.director):
            self.client.force_login(user)
            response = self.client.post(reverse("patients:archive", args=(self.patient.pk,)))
            self.assertEqual(response.status_code, 403)

    def test_archive_endpoint_requires_post(self):
        self.client.force_login(self.registrar)
        self.assertEqual(self.client.get(reverse("patients:archive", args=(self.patient.pk,))).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.registrar)
        csrf_response = csrf_client.post(reverse("patients:archive", args=(self.patient.pk,)))
        self.assertEqual(csrf_response.status_code, 403)

    def test_list_defaults_to_active_and_preserves_selected_scope_in_search(self):
        archived = Patient.objects.create(
            last_name="Архивная", first_name="Анна", birth_date="1991-01-01", sex="female",
            phone="+79003334455", city="Иркутск", street="Ленина", house="3", is_archived=True,
        )
        self.client.force_login(self.registrar)
        default_response = self.client.get(reverse("patients:list"))
        self.assertContains(default_response, self.patient.full_name)
        self.assertNotContains(default_response, archived.full_name)

        archived_response = self.client.get(reverse("patients:list"), {"scope": "archived", "q": "Архивная"})
        self.assertContains(archived_response, archived.full_name)
        self.assertContains(archived_response, 'name="scope" value="archived"', html=False)


class PatientAdminSafetyTests(TestCase):
    def test_delete_and_direct_archive_field_editing_are_disabled(self):
        model_admin = PatientAdmin(Patient, admin.site)
        request = RequestFactory().get("/admin/patients/patient/")
        request.user = User(is_superuser=True, is_staff=True, role=User.Role.ADMINISTRATOR)
        self.assertFalse(model_admin.has_delete_permission(request))
        admin_form = model_admin.get_form(request)
        for field in ("is_archived", "archived_at", "archived_by", "archive_reason"):
            self.assertNotIn(field, admin_form.base_fields)
