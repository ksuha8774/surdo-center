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

from .calculations import CALCULATION_VERSION, calculate_exam, calculate_indicators
from .decision_support import evaluate_condition, run_decision_analysis, validate_condition
from .forms import AudiometryExamForm, AudiometryMeasurementGridForm
from .models import (
    AudiometryExam,
    AudiometryMeasurement,
    DecisionAnalysis,
    DecisionRule,
    DecisionRuleSet,
)
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


class AudiometryCalculationTests(AudiometryFixtureMixin, TestCase):
    def add_threshold(self, ear, conduction, frequency, value, *, masked=False, no_response=False):
        return AudiometryMeasurement.objects.create(
            exam=self.exam,
            ear=ear,
            conduction_type=conduction,
            frequency_hz=frequency,
            threshold_db_hl=None if no_response else value,
            no_response=no_response,
            no_response_level_db_hl=value if no_response else None,
            masked=masked,
        )

    def add_complete_air_series(self, ear, values, *, masked=False):
        for frequency, value in zip((500, 1000, 2000, 4000), values):
            self.add_threshold(ear, "air", frequency, value, masked=masked)

    def test_pta3_pta4_and_interaural_difference_use_control_values(self):
        self.add_complete_air_series("right", (10, 20, 30, 40))
        self.add_complete_air_series("left", (20, 30, 40, 50))
        result = calculate_indicators(self.exam.measurements.all())
        self.assertEqual(result.pta3_right, 20)
        self.assertEqual(result.pta4_right, 25)
        self.assertEqual(result.pta3_left, 30)
        self.assertEqual(result.pta4_left, 35)
        self.assertEqual(result.pta4_interaural_difference, 10)

    def test_missing_frequency_and_no_response_do_not_become_zero(self):
        self.add_threshold("right", "air", 500, 20)
        self.add_threshold("right", "air", 1000, 30)
        self.add_threshold("right", "air", 2000, 100, no_response=True)
        self.add_threshold("right", "air", 4000, 40)
        result = calculate_indicators(self.exam.measurements.all())
        self.assertIsNone(result.pta3_right)
        self.assertIsNone(result.pta4_right)
        self.assertIn(2000, result.completeness["ears"]["right"]["missing_pta4_frequencies"])

    def test_masked_air_threshold_is_preferred_for_pta(self):
        self.add_complete_air_series("right", (10, 10, 10, 10))
        self.add_threshold("right", "air", 1000, 50, masked=True)
        result = calculate_indicators(self.exam.measurements.all())
        self.assertEqual(result.pta4_right, 20)

    def test_abg_matches_same_frequency_ear_and_masking_only(self):
        self.add_threshold("right", "air", 1000, 50, masked=True)
        self.add_threshold("right", "bone", 1000, 20, masked=True)
        self.add_threshold("right", "air", 2000, 45, masked=True)
        self.add_threshold("right", "bone", 2000, 10, masked=False)
        self.add_threshold("left", "bone", 1000, 5, masked=True)
        result = calculate_indicators(self.exam.measurements.all())
        self.assertEqual(result.abg_by_frequency["right"]["1000"]["value"], 30.0)
        self.assertNotIn("2000", result.abg_by_frequency["right"])
        self.assertEqual(result.max_abg_right, 30)

    def test_recalculation_updates_saved_result_after_measurement_change(self):
        self.add_complete_air_series("right", (10, 20, 30, 40))
        calculation, _ = calculate_exam(self.exam)
        self.assertEqual(calculation.pta4_right, 25)
        measurement = self.exam.measurements.get(ear="right", conduction_type="air", frequency_hz=4000)
        measurement.threshold_db_hl = 80
        measurement.save(update_fields=("threshold_db_hl",))
        self.exam.updated_at = timezone.now()
        self.exam.save(update_fields=("updated_at",))
        calculation, _ = calculate_exam(self.exam)
        self.assertEqual(calculation.pta4_right, 35)
        self.assertEqual(calculation.calculation_version, CALCULATION_VERSION)


class DecisionSupportTests(AudiometryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        for frequency, value in zip((500, 1000, 2000, 4000), (20, 30, 40, 50)):
            AudiometryMeasurement.objects.create(
                exam=self.exam,
                ear=AudiometryMeasurement.Ear.RIGHT,
                conduction_type=AudiometryMeasurement.ConductionType.AIR,
                frequency_hz=frequency,
                threshold_db_hl=value,
            )
        self.rule_set = DecisionRuleSet.objects.create(
            code="audiometry-test",
            name="Тестовый набор аудиометрии",
            version="test-1",
            is_active=True,
            is_test=True,
        )

    def create_rule(self, *, code="test-rule", condition=None):
        return DecisionRule.objects.create(
            rule_set=self.rule_set,
            code=code,
            title="Тестовое правило",
            condition=condition or {"metric": "pta4_right", "operator": "gte", "value": 35},
            result_text="Тестовый предварительный вывод",
            recommendation_text="Тестовая рекомендация",
        )

    def test_logical_conditions_support_all_any_and_preserve_evidence(self):
        condition = {
            "all": [
                {"metric": "pta4_right", "operator": "gte", "value": 35},
                {"any": [
                    {"metric": "pta4_left", "operator": "missing"},
                    {"metric": "pta4_left", "operator": "gt", "value": 10},
                ]},
            ]
        }
        validate_condition(condition)
        result = evaluate_condition(condition, {"pta4_right": 35.0, "pta4_left": None})
        self.assertTrue(result.matched)
        self.assertEqual({item["metric"] for item in result.evidence}, {"pta4_right", "pta4_left"})

    def test_analysis_saves_snapshot_rule_version_hit_and_explanation(self):
        rule = self.create_rule()
        analysis = run_decision_analysis(self.exam, self.doctor, self.rule_set)
        self.assertEqual(analysis.rule_set.version, "test-1")
        self.assertEqual(analysis.calculated_values["pta4_right"], 35.0)
        self.assertEqual(len(analysis.input_snapshot), 4)
        hit = analysis.rule_hits.get(rule=rule)
        self.assertIn("фактическое значение 35.0", hit.explanation)
        self.assertEqual(hit.evidence[0]["actual"], 35.0)
        self.assertIn("тестовый набор", " ".join(analysis.warnings).lower())

    def test_repeated_analysis_keeps_history(self):
        self.create_rule()
        first = run_decision_analysis(self.exam, self.doctor, self.rule_set)
        second = run_decision_analysis(self.exam, self.doctor, self.rule_set)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(DecisionAnalysis.objects.filter(exam=self.exam).count(), 2)
        self.assertEqual(first.data_hash, second.data_hash)

    def test_previous_analysis_becomes_stale_after_measurement_change(self):
        self.create_rule()
        analysis = run_decision_analysis(self.exam, self.doctor, self.rule_set)
        measurement = self.exam.measurements.get(frequency_hz=4000)
        measurement.threshold_db_hl = 70
        measurement.save(update_fields=("threshold_db_hl",))
        self.exam.updated_at = timezone.now() + timedelta(seconds=1)
        self.exam.save(update_fields=("updated_at",))
        analysis = DecisionAnalysis.objects.select_related("exam").get(pk=analysis.pk)
        self.assertTrue(analysis.is_stale)

    def test_analysis_without_active_rules_returns_quantitative_warning(self):
        self.rule_set.is_active = False
        self.rule_set.save(update_fields=("is_active",))
        analysis = run_decision_analysis(self.exam, self.doctor)
        self.assertIsNone(analysis.rule_set)
        self.assertEqual(analysis.rule_hits.count(), 0)
        self.assertIn("не настроен", " ".join(analysis.warnings).lower())
