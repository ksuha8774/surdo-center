from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Doctor, User
from audiometry.models import AudiometryExam
from billing.models import Service
from patients.models import Patient
from scheduling.models import Appointment
from .models import MedicalVisit


class MedicalVisitWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="visit-doctor", password="pass12345", role=User.Role.DOCTOR,
            first_name="Мария", last_name="Соколова",
        )
        self.doctor = Doctor.objects.create(user=self.user, specialization="Сурдолог")
        self.patient = Patient.objects.create(
            last_name="Иванов", first_name="Павел", birth_date="1985-08-20",
            sex=Patient.Sex.MALE, phone="+79000000102", city="Иркутск",
        )
        self.service = Service.objects.create(
            service_name="Диагностика слуха", price="2500.00", duration_minutes=60,
            medical_form_type="primary",
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            planned_service=self.service,
            appointment_date=timezone.localdate() + timedelta(days=1),
            start_time=time(10),
            end_time=time(11),
        )
        self.url = reverse("medical:edit", args=(self.appointment.pk,))
        self.client.force_login(self.user)

    @staticmethod
    def form_data(**overrides):
        data = {
            "complaints": "Снижение слуха",
            "anamnesis": "Жалобы около года",
            "examination_result": "Без воспалительных изменений",
            "conclusion": "",
            "recommendations": "Контрольный приём",
            "save": "1",
        }
        data.update(overrides)
        return data

    def test_workspace_uses_compact_sections_without_removed_patient_card(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Данные осмотра")
        self.assertContains(response, "Итоги приёма")
        self.assertContains(response, "К списку приёмов")
        self.assertNotContains(response, "Предыдущие приёмы")
        self.assertNotContains(response, self.patient.phone)

    def test_draft_saves_all_five_fields(self):
        response = self.client.post(self.url, self.form_data())
        self.assertRedirects(response, reverse("scheduling:detail", args=(self.appointment.pk,)))
        visit = MedicalVisit.objects.get(appointment=self.appointment)
        self.assertEqual(visit.complaints, "Снижение слуха")
        self.assertEqual(visit.anamnesis, "Жалобы около года")
        self.assertEqual(visit.examination_result, "Без воспалительных изменений")
        self.assertEqual(visit.recommendations, "Контрольный приём")

    def test_audiometry_action_saves_draft_and_reuses_existing_exam(self):
        self.service.medical_form_type = "legacy"
        self.service.save()
        self.client.get(self.url)
        visit = MedicalVisit.objects.get(appointment=self.appointment)
        response = self.client.post(self.url, self.form_data(audiometry="1", save=""))
        self.assertRedirects(response, reverse("audiometry:create_for_visit", args=(visit.pk,)))
        visit.refresh_from_db()
        self.assertEqual(visit.complaints, "Снижение слуха")

        exam = AudiometryExam.objects.create(
            patient=self.patient, visit=visit, performed_by=self.doctor,
        )
        response = self.client.post(
            self.url,
            self.form_data(complaints="Обновлённые жалобы", audiometry="1", save=""),
        )
        self.assertRedirects(response, reverse("audiometry:detail", args=(exam.pk,)))
        self.assertEqual(visit.audiometry_exams.count(), 1)
        visit.refresh_from_db()
        self.assertEqual(visit.complaints, "Обновлённые жалобы")

    def test_completed_visit_is_read_only_and_cannot_be_completed_twice(self):
        response = self.client.post(
            self.url,
            self.form_data(conclusion="Двусторонняя тугоухость", complete="1", save=""),
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.COMPLETED)
        self.assertContains(self.client.get(self.url), "только для просмотра")
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)
        visit = MedicalVisit.objects.get(appointment=self.appointment)
        snapshot = visit.form_snapshot
        self.service.medical_form_type = "brief"
        self.service.medical_form_version = 2
        self.service.save()
        response = self.client.get(self.url)
        self.assertEqual(response.context["visit"].form_snapshot, snapshot)
        self.assertContains(response, "Данные осмотра")

    def test_service_form_selection_and_only_configured_fields(self):
        cases = {
            "brief": ["complaints", "conclusion", "recommendations"],
            "repeat": ["complaints", "anamnesis", "examination_result", "conclusion", "recommendations"],
            "hearing_diagnostic": ["conclusion", "recommendations"],
            "results": ["complaints", "examination_result", "conclusion", "recommendations"],
            "extended": ["complaints", "conclusion", "recommendations"],
        }
        from .models import MedicalVisit
        for code, names in cases.items():
            with self.subTest(code=code):
                MedicalVisit.objects.filter(appointment=self.appointment).delete()
                self.service.medical_form_type = code
                self.service.save()
                response = self.client.get(self.url)
                self.assertEqual(list(response.context["form"].fields), names)
                self.assertEqual(response.context["has_audiometry"], code == "hearing_diagnostic")
                self.assertEqual(response.context["visit"].form_type, code)

    def test_draft_keeps_snapshot_when_service_changes_or_is_renamed(self):
        self.client.post(self.url, self.form_data())
        self.service.medical_form_type = "brief"
        self.service.service_name = "Новое название"
        self.service.save()
        response = self.client.get(self.url)
        self.assertEqual(response.context["visit"].form_type, "primary")
        self.assertIn("anamnesis", response.context["form"].fields)
        self.assertEqual(response.context["form"]["complaints"].value(), "Снижение слуха")

    def test_completion_checks_current_configuration_but_not_draft(self):
        response = self.client.post(self.url, self.form_data(complete="1"))
        self.assertContains(response, "Перед завершением")
        self.assertFalse(MedicalVisit.objects.get(appointment=self.appointment).completed_at)

    def test_other_doctor_cannot_read_or_write_visit(self):
        user = User.objects.create_user(username="other-visit", password="pass12345", role=User.Role.DOCTOR)
        Doctor.objects.create(user=user)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)

    def test_configured_additional_fields_and_completion_module(self):
        from copy import deepcopy
        from .configurations import get_configuration
        from .forms import MedicalVisitForm
        visit = MedicalVisit.objects.create(appointment=self.appointment)
        config = get_configuration("extended")
        config["sections"][0]["fields"].append(dict(name="extra_note", label="Согласованный раздел", kind="text", required=True))
        config["completion_modules"] = ["audiometry"]
        form = MedicalVisitForm({"extra_note": "Заполнено"}, instance=visit, configuration=deepcopy(config))
        self.assertTrue(form.is_valid())
        form.save()
        visit.refresh_from_db()
        self.assertEqual(visit.additional_data["extra_note"], "Заполнено")
        form = MedicalVisitForm({"complete": "1", "extra_note": "Заполнено"}, instance=visit, configuration=config)
        self.assertFalse(form.is_valid())
        self.assertIn("завершённое аудиометрическое", str(form.errors))

    def test_migration_preserves_existing_values_and_completed_snapshot(self):
        from importlib import import_module
        from django.apps import apps
        visit = MedicalVisit.objects.create(appointment=self.appointment, **{
            key: value for key, value in self.form_data(conclusion="Старое заключение").items() if key != "save"
        })
        before = tuple(getattr(visit, key) for key in ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations"))
        import_module("medical.migrations.0004_preserve_existing_documents").preserve(apps, None)
        visit.refresh_from_db()
        self.assertEqual(before, tuple(getattr(visit, key) for key in ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations")))
        self.assertEqual(visit.form_type, "legacy")
