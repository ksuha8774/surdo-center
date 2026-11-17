from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Doctor, User
from billing.models import Service
from medical.models import MedicalVisit
from patients.models import Patient
from scheduling.models import Appointment

from .forms import AudiometryExamForm, AudiometryMeasurementGridForm
from .models import AudiometryExam, AudiometryMeasurement
from .services import can_edit_exam, can_view_exam, save_exam


class AudiometryFixtureMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            username="audio-doctor", password="pass12345", role=User.Role.DOCTOR,
        )
        self.doctor = Doctor.objects.create(user=self.user)
        self.patient = Patient.objects.create(
            last_name="Сидорова", first_name="Анна", birth_date="1992-01-01", sex="female",
            phone="+79000000002", city="Иркутск", street="Советская", house="3",
        )
        service = Service.objects.create(service_name="Аудиометрия", price=1000, duration_minutes=45)
        appointment = Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, planned_service=service, planned_price=service.price,
            appointment_date=timezone.localdate() + timedelta(days=1), start_time=time(9), end_time=time(9, 45),
        )
        self.visit = MedicalVisit.objects.create(appointment=appointment)
        self.exam = AudiometryExam.objects.create(visit=self.visit, performed_by=self.doctor)


class AudiometryModelTests(AudiometryFixtureMixin, TestCase):
    def test_exam_infers_patient_from_visit(self):
        self.assertEqual(self.exam.patient, self.patient)
        self.assertEqual(self.exam.status, AudiometryExam.Status.DRAFT)

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
        measurement = AudiometryMeasurement(
            exam=self.exam, ear="right", conduction_type="bone", frequency_hz=2000,
            no_response=True, threshold_db_hl=80,
        )
        with self.assertRaises(ValidationError):
            measurement.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            measurement.save()

    def test_no_response_is_stored_without_fake_threshold(self):
        measurement = AudiometryMeasurement(
            exam=self.exam, ear="right", conduction_type="air", frequency_hz=4000,
            no_response=True, no_response_level_db_hl=110,
        )
        measurement.full_clean()
        measurement.save()
        measurement.refresh_from_db()
        self.assertIsNone(measurement.threshold_db_hl)
        self.assertEqual(measurement.no_response_level_db_hl, 110)

    def test_non_standard_frequency_is_rejected(self):
        measurement = AudiometryMeasurement(
            exam=self.exam, ear="left", conduction_type="air", frequency_hz=333,
            threshold_db_hl=20,
        )
        with self.assertRaises(ValidationError):
            measurement.full_clean()


class AudiometrySavingTests(AudiometryFixtureMixin, TestCase):
    def metadata_form(self, *, complete=False):
        value = timezone.localtime(self.exam.exam_datetime).strftime("%Y-%m-%dT%H:%M")
        form = AudiometryExamForm({
            "exam_datetime": value,
            "exam_type": AudiometryExam.ExamType.PURE_TONE,
            "reliability": AudiometryExam.Reliability.RELIABLE,
            "equipment_model": "Тестовый аудиометр",
            "comment": "Черновые данные",
            "doctor_conclusion": "Заключение врача" if complete else "",
            "doctor_recommendations": "",
        }, instance=self.exam, completing=complete)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def grid_form(self):
        form = AudiometryMeasurementGridForm({
            "right_air_plain_reliability": AudiometryMeasurement.Reliability.RELIABLE,
            "right_air_plain_500_threshold": "20",
            "right_air_plain_1000_threshold": "25",
            "left_bone_masked_reliability": AudiometryMeasurement.Reliability.QUESTIONABLE,
            "left_bone_masked_2000_no_response": "on",
            "left_bone_masked_2000_level": "95",
        })
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_draft_saves_structured_measurements_without_losing_no_response(self):
        exam = save_exam(
            exam=self.exam,
            metadata_form=self.metadata_form(),
            measurement_form=self.grid_form(),
        )
        self.assertEqual(exam.status, AudiometryExam.Status.DRAFT)
        self.assertEqual(exam.measurements.count(), 3)
        no_response = exam.measurements.get(ear="left", conduction_type="bone", frequency_hz=2000, masked=True)
        self.assertTrue(no_response.no_response)
        self.assertIsNone(no_response.threshold_db_hl)
        self.assertEqual(no_response.no_response_level_db_hl, 95)

    def test_completion_locks_exam_for_ordinary_editing(self):
        exam = save_exam(
            exam=self.exam,
            metadata_form=self.metadata_form(complete=True),
            measurement_form=self.grid_form(),
            complete=True,
        )
        self.assertEqual(exam.status, AudiometryExam.Status.COMPLETED)
        self.assertIsNotNone(exam.completed_at)
        self.assertTrue(can_view_exam(self.user, exam))
        self.assertFalse(can_edit_exam(self.user, exam))
