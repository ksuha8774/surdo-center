from datetime import time, timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier, Thread

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Doctor, User
from audiometry.models import AudiometryExam, AudiometryMeasurement
from billing.models import Payment, ProvidedService, Service
from medical.models import MedicalVisit
from scheduling.models import Appointment

from .admin import PatientAdmin
from .forms import PatientForm
from .models import Patient, PatientArchiveEvent
from .services import (
    DuplicatePatientError,
    archive_patient,
    normalize_name_part,
    normalize_phone_for_search,
    restore_patient,
    save_patient_form,
)


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

    def test_patient_can_be_created_without_middle_name_or_address(self):
        form = PatientForm(data={
            "last_name": "Сидорова", "first_name": "Мария", "middle_name": "",
            "birth_date": "1992-04-10", "sex": "female", "phone": "+79004445566",
            "email": "", "city": "", "street": "", "house": "", "apartment": "", "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save()
        self.assertEqual(patient.middle_name, "")
        self.assertEqual(patient.full_address, "Не указан")

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
        with self.assertRaises(DuplicatePatientError):
            Patient.objects.create(
                last_name="иванов", first_name="Иван", middle_name="Иванович",
                birth_date="1990-01-01", sex="male", phone="+79001112233",
            )

    def test_old_phone_format_and_random_name_spaces_are_normalized_for_duplicates(self):
        existing = Patient.objects.create(
            last_name="  ИВАНОВ  ", first_name="Иван", middle_name="",
            birth_date="1990-01-01", sex="male", phone="8 (900) 111-22-33",
        )
        form = PatientForm(data={
            "last_name": "иванов", "first_name": "  Иван ", "middle_name": "",
            "birth_date": "1990-01-01", "sex": "male", "phone": "+7 900 111 22 33",
            "email": "", "city": "", "street": "", "house": "", "apartment": "", "note": "",
        })
        self.assertFalse(form.is_valid())
        self.assertEqual(form.exact_duplicate, existing)

    def test_partial_duplicate_requires_confirmation_but_phone_only_match_does_not(self):
        Patient.objects.create(
            last_name="Петров", first_name="Пётр", middle_name="Петрович",
            birth_date="1980-02-03", sex="male", phone="+79001110000",
        )
        partial_data = {
            "last_name": "Петров", "first_name": "Пётр", "middle_name": "Петрович",
            "birth_date": "1980-02-03", "sex": "male", "phone": "+79002220000",
            "email": "", "city": "", "street": "", "house": "", "apartment": "", "note": "",
        }
        self.assertFalse(PatientForm(data=partial_data).is_valid())
        self.assertTrue(PatientForm(data={**partial_data, "confirm_duplicate": "on"}).is_valid())

        phone_only = PatientForm(data={
            **partial_data,
            "last_name": "Сидоров",
            "first_name": "Сидор",
            "middle_name": "",
            "birth_date": "1995-06-07",
            "phone": "+79001110000",
        })
        self.assertTrue(phone_only.is_valid(), phone_only.errors)
        phone_only.save()
        self.assertEqual(Patient.objects.filter(phone="+79001110000").count(), 2)


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
        self.assertEqual(
            list(self.patient.archive_events.values_list("action", flat=True).order_by("pk")),
            [PatientArchiveEvent.Action.ARCHIVED, PatientArchiveEvent.Action.RESTORED],
        )

        archived_again, _ = archive_patient(patient=restored, actor=self.registrar, reason="Повторный цикл")
        restore_patient(patient=archived_again, actor=self.registrar)
        self.assertEqual(self.patient.archive_events.count(), 4)

    def test_unfinished_appointment_blocks_archiving_without_cancelling_it(self):
        appointment = self._appointment(status=Appointment.Status.IN_PROGRESS)
        with self.assertRaisesMessage(ValidationError, "есть незавершённая запись"):
            archive_patient(patient=self.patient, actor=self.registrar)
        self.patient.refresh_from_db()
        appointment.refresh_from_db()
        self.assertFalse(self.patient.is_archived)
        self.assertEqual(appointment.status, Appointment.Status.IN_PROGRESS)

    def test_overdue_planned_appointment_still_blocks_archiving(self):
        appointment = self._appointment(status=Appointment.Status.PLANNED)
        Appointment.objects.filter(pk=appointment.pk).update(
            appointment_date=timezone.localdate() - timedelta(days=30)
        )
        with self.assertRaisesMessage(ValidationError, "есть незавершённая запись"):
            archive_patient(patient=self.patient, actor=self.registrar)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.PLANNED)

    def test_related_medical_and_billing_data_survive_archiving(self):
        appointment = self._appointment(status=Appointment.Status.COMPLETED)
        cancelled = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, created_by=self.registrar,
            planned_service=self.service, planned_price=self.service.price,
            appointment_date=timezone.localdate(), start_time=time(10), end_time=time(10, 30),
            status=Appointment.Status.CANCELLED,
        )
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
        self.assertTrue(Appointment.objects.filter(pk=cancelled.pk).exists())
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

    def test_duplicate_endpoint_uses_same_rules_and_links_archived_exact_match(self):
        self.patient.last_name = "  ПЕТРОВ "
        self.patient.phone = "8 (900) 222-33-44"
        self.patient.is_archived = True
        self.patient.save(update_fields=("last_name", "phone", "is_archived"))
        self.client.force_login(self.registrar)

        response = self.client.post(reverse("patients:duplicates"), {
            "last_name": "петров",
            "first_name": "Пётр",
            "middle_name": "",
            "birth_date": "1988-02-03",
            "phone": "+7 900 222 33 44",
        })
        self.assertEqual(response.status_code, 200)
        result = response.json()["patients"][0]
        self.assertEqual(result["id"], self.patient.pk)
        self.assertTrue(result["is_exact_duplicate"])
        self.assertTrue(result["is_archived"])
        self.assertEqual(result["url"], reverse("patients:detail", args=(self.patient.pk,)))

    def test_universal_search_handles_full_name_old_phone_format_and_birth_date(self):
        searchable = Patient.objects.create(
            last_name="Иванова", first_name="Анна", middle_name="Сергеевна",
            birth_date="1993-07-08", sex="female", phone="8 (901) 222-33-44",
        )
        Patient.objects.create(
            last_name="Иванова", first_name="Мария", middle_name="Сергеевна",
            birth_date="1980-01-01", sex="female", phone="+79019998877",
        )
        self.client.force_login(self.registrar)

        by_name = self.client.get(reverse("patients:list"), {"q": "  анна   иванова "})
        self.assertContains(by_name, searchable.full_name)
        self.assertNotContains(by_name, "Иванова Мария Сергеевна")

        by_phone = self.client.get(reverse("patients:list"), {"q": "+7 (901) 222-33-44"})
        self.assertContains(by_phone, searchable.full_name)
        by_phone_part = self.client.get(reverse("patients:list"), {"q": "+7 901"})
        self.assertContains(by_phone_part, searchable.full_name)

        by_birth_date = self.client.get(
            reverse("patients:list"), {"q": "Иванова", "birth_date": "1993-07-08"}
        )
        self.assertContains(by_birth_date, searchable.full_name)
        self.assertNotContains(by_birth_date, "Иванова Мария Сергеевна")

    def test_archived_patient_cannot_be_edited_and_director_cannot_open_registry(self):
        archive_patient(patient=self.patient, actor=self.registrar)
        self.client.force_login(self.registrar)
        edit_url = reverse("patients:edit", args=(self.patient.pk,))
        self.assertRedirects(self.client.get(edit_url), reverse("patients:detail", args=(self.patient.pk,)) + "?return_to=%2Fpatients%2F")

        response = self.client.post(edit_url, {
            "last_name": "Изменён", "first_name": self.patient.first_name, "middle_name": "",
            "birth_date": self.patient.birth_date, "sex": self.patient.sex, "phone": self.patient.phone,
            "email": "", "city": "", "street": "", "house": "", "apartment": "", "note": "",
        })
        self.assertEqual(response.status_code, 302)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.last_name, "Петров")

        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse("patients:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("patients:detail", args=(self.patient.pk,))).status_code, 403)
        self.assertEqual(self.client.get(reverse("scheduling:list")).status_code, 403)


class PatientDuplicateAuditCommandTests(TestCase):
    def test_command_is_read_only_when_database_has_no_duplicates(self):
        Patient.objects.create(
            last_name="Демонстрационный", first_name="Павел", birth_date="1985-08-20",
            sex="male", phone="8 900 000-10-02",
        )
        output = StringIO()
        call_command("audit_patient_duplicates", stdout=output)
        report = output.getvalue()
        self.assertIn("Полных дублей не найдено", report)
        self.assertEqual(Patient.objects.count(), 1)


class DoctorPatientHistoryAccessTests(TestCase):
    def setUp(self):
        viewer_user = User.objects.create_user(
            username="history-viewer", password="pass12345", role=User.Role.DOCTOR,
        )
        author_user = User.objects.create_user(
            username="history-author", password="pass12345", role=User.Role.DOCTOR,
        )
        self.viewer = Doctor.objects.create(user=viewer_user)
        self.author = Doctor.objects.create(user=author_user)
        self.registrar = User.objects.create_user(
            username="history-registrar", password="pass12345", role=User.Role.ADMINISTRATOR,
        )
        self.patient = Patient.objects.create(
            last_name="История", first_name="Пациента", birth_date="1984-03-02",
            sex="female", phone="+79006667788",
        )
        service = Service.objects.create(
            service_name="Историческое обследование", price=Decimal("2500.00"), duration_minutes=60,
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.author, created_by=self.registrar,
            planned_service=service, planned_price=service.price,
            appointment_date=timezone.localdate() - timedelta(days=10),
            start_time=time(10), end_time=time(11), status=Appointment.Status.COMPLETED,
        )
        visit = MedicalVisit.objects.create(
            appointment=self.appointment,
            conclusion="Заключение другого врача",
            recommendations="Контроль через год",
        )
        visit.completed_at = timezone.now()
        visit.save(update_fields=("completed_at",))
        exam_time = timezone.now()
        exam = AudiometryExam.objects.create(
            visit=visit, performed_by=self.author, comment="Аудиограмма другого врача",
            exam_datetime=exam_time, completed_at=exam_time,
        )
        AudiometryMeasurement.objects.create(
            exam=exam,
            ear=AudiometryMeasurement.Ear.RIGHT,
            conduction_type=AudiometryMeasurement.ConductionType.AIR,
            frequency_hz=1000,
            threshold_db_hl=Decimal("25.0"),
        )

    def test_doctor_sees_other_doctors_read_only_medical_history(self):
        self.client.force_login(self.viewer.user)
        response = self.client.get(reverse("patients:detail", args=(self.patient.pk,)))
        self.assertContains(response, "Заключение другого врача")
        self.assertContains(response, "Аудиограмма другого врача")
        self.assertContains(response, "1000 Гц")

        edit_response = self.client.get(reverse("medical:edit", args=(self.appointment.pk,)))
        self.assertEqual(edit_response.status_code, 403)

    def test_registrar_does_not_receive_medical_conclusions_in_patient_card(self):
        self.client.force_login(self.registrar)
        response = self.client.get(reverse("patients:detail", args=(self.patient.pk,)))
        self.assertNotContains(response, "Заключение другого врача")


class PatientAdminSafetyTests(TestCase):
    def test_delete_and_direct_archive_field_editing_are_disabled(self):
        model_admin = PatientAdmin(Patient, admin.site)
        request = RequestFactory().get("/admin/patients/patient/")
        request.user = User(is_superuser=True, is_staff=True, role=User.Role.ADMINISTRATOR)
        self.assertFalse(model_admin.has_delete_permission(request))
        admin_form = model_admin.get_form(request)
        for field in ("is_archived", "archived_at", "archived_by", "archive_reason"):
            self.assertNotIn(field, admin_form.base_fields)


class PatientDatabaseUniquenessTests(TestCase):
    def test_postgresql_normalization_matches_django(self):
        phone_values = (
            "8 (900) 111-22-33",
            "79001112233",
            "9001112233",
            "+7 900 111 22 33",
            "+44 20 7946 0958",
            "invalid-phone",
        )
        name_values = ("  ИВАНОВ  ", "Ива   нов", "", "  Anna Maria ")
        with connection.cursor() as cursor:
            for value in phone_values:
                cursor.execute("SELECT patients_normalize_phone(%s)", [value])
                self.assertEqual(cursor.fetchone()[0], normalize_phone_for_search(value))
            for value in name_values:
                cursor.execute("SELECT patients_normalize_name(%s)", [value])
                self.assertEqual(cursor.fetchone()[0], normalize_name_part(value))

    def test_bulk_create_cannot_bypass_normalized_unique_index(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.bulk_create([
                Patient(
                    last_name="Иванов", first_name="Иван", middle_name="",
                    birth_date="1990-01-01", sex="male", phone="8 (900) 111-22-33",
                ),
                Patient(
                    last_name="  иванов ", first_name="ИВАН", middle_name="   ",
                    birth_date="1990-01-01", sex="male", phone="+7 900 111 22 33",
                ),
            ])
        self.assertFalse(Patient.objects.exists())

    def test_queryset_update_cannot_create_normalized_duplicate(self):
        primary = Patient.objects.create(
            last_name="Smith", first_name="Anna", middle_name="",
            birth_date="1987-04-03", sex="female", phone="+44 20 7946 0958",
        )
        other = Patient.objects.create(
            last_name="Brown", first_name="Mary", middle_name="Jane",
            birth_date="1992-05-06", sex="female", phone="+33142345678",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.filter(pk=other.pk).update(
                last_name=" smith ",
                first_name="ANNA",
                middle_name=" ",
                birth_date=primary.birth_date,
                phone="+442079460958",
            )
        other.refresh_from_db()
        self.assertEqual(other.last_name, "Brown")

    def test_direct_sql_cannot_create_normalized_duplicate(self):
        primary = Patient.objects.create(
            last_name="Петров", first_name="Пётр", middle_name="",
            birth_date="1985-02-01", sex="male", phone="+79007778899",
        )
        other = Patient.objects.create(
            last_name="Сидоров", first_name="Сидор", middle_name="Иванович",
            birth_date="1991-03-02", sex="male", phone="+79000000001",
        )
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE patients_patient
                SET last_name = %s, first_name = %s, middle_name = %s,
                    birth_date = %s, phone = %s
                WHERE id = %s
                """,
                [" петров ", "ПЁТР", " ", primary.birth_date, "8 (900) 777-88-99", other.pk],
            )
        other.refresh_from_db()
        self.assertEqual(other.last_name, "Сидоров")


class ConcurrentPatientCreationTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_full_duplicate_is_rejected_by_application_lock(self):
        barrier = Barrier(2)
        results = []
        data = {
            "last_name": "Конкурентный", "first_name": "Пациент", "middle_name": "",
            "birth_date": "1990-01-01", "sex": "male", "phone": "+79005556677",
            "email": "", "city": "", "street": "", "house": "", "apartment": "", "note": "",
        }

        def create_patient():
            close_old_connections()
            try:
                form = PatientForm(data=data)
                if not form.is_valid():
                    results.append("rejected")
                    return
                barrier.wait()
                save_patient_form(form)
            except DuplicatePatientError:
                results.append("rejected")
            else:
                results.append("created")
            finally:
                connections.close_all()

        threads = [Thread(target=create_patient) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sorted(results), ["created", "rejected"])
        self.assertEqual(Patient.objects.count(), 1)


class PatientUniqueMigrationTests(TransactionTestCase):
    migrate_from = ("patients", "0004_alter_patient_city_alter_patient_house_and_more")
    migrate_to = ("patients", "0005_patient_normalized_identity_unique")

    def test_migration_can_be_reversed_and_reapplied(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([self.migrate_from])
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regprocedure(%s), to_regclass(%s)",
                    ["patients_normalize_phone(text)", "patients_patient_normalized_identity_uniq"],
                )
                self.assertEqual(cursor.fetchone(), (None, None))

            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regprocedure(%s) IS NOT NULL, to_regclass(%s) IS NOT NULL",
                    ["patients_normalize_phone(text)", "patients_patient_normalized_identity_uniq"],
                )
                self.assertEqual(cursor.fetchone(), (True, True))
        finally:
            MigrationExecutor(connection).migrate([self.migrate_to])
