import json
from collections import defaultdict

from django.core.management.base import BaseCommand

from audiometry.models import AudiometryExam
from billing.models import Payment, ProvidedService
from integrations.models import ExternalBookingRequest
from medical.models import MedicalVisit
from patients.models import Patient
from patients.services import normalize_name_part, normalize_phone_for_search
from scheduling.models import Appointment


class Command(BaseCommand):
    help = "Только чтение: находит полные дубли пациентов и показывает связанные данные."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Вывести отчёт в JSON.")

    def handle(self, *args, **options):
        groups = defaultdict(list)
        for patient in Patient.objects.all().order_by("pk"):
            normalized_phone = normalize_phone_for_search(patient.phone)
            if not normalized_phone:
                continue
            key = (
                normalize_name_part(patient.last_name),
                normalize_name_part(patient.first_name),
                normalize_name_part(patient.middle_name),
                patient.birth_date.isoformat(),
                normalized_phone,
            )
            groups[key].append(patient)

        duplicate_groups = [patients for patients in groups.values() if len(patients) > 1]
        report = [self._serialize_group(index, patients) for index, patients in enumerate(duplicate_groups, start=1)]

        if options["as_json"]:
            self.stdout.write(json.dumps({"duplicate_groups": report}, ensure_ascii=False, indent=2, default=str))
            return

        if not report:
            self.stdout.write(self.style.SUCCESS("Полных дублей не найдено."))
            return

        self.stdout.write(self.style.WARNING(f"Найдено групп полных дублей: {len(report)}"))
        for group in report:
            self.stdout.write(f"\nГруппа {group['group']}: {group['identity']}")
            for patient in group["patients"]:
                status = "в архиве" if patient["is_archived"] else "активен"
                self.stdout.write(
                    f"  Patient ID={patient['id']} ({status}); "
                    f"приёмы={patient['appointments']}; медицинские приёмы={patient['visit_ids']}; "
                    f"аудиометрия={patient['audiometry_exam_ids']}; услуги={patient['provided_service_ids']}; "
                    f"оплаты={patient['payment_ids']}; внешние запросы={patient['external_request_ids']}"
                )
        self.stdout.write("\nДанные не изменялись. Автоматическое удаление или объединение не выполнялось.")

    def _serialize_group(self, index, patients):
        first = patients[0]
        return {
            "group": index,
            "identity": {
                "full_name": first.full_name,
                "birth_date": first.birth_date.isoformat(),
                "normalized_phone": normalize_phone_for_search(first.phone),
            },
            "patients": [self._serialize_patient(patient) for patient in patients],
        }

    @staticmethod
    def _serialize_patient(patient):
        appointment_ids = list(
            Appointment.objects.filter(patient=patient).order_by("pk").values_list("pk", flat=True)
        )
        visit_ids = list(
            MedicalVisit.objects.filter(appointment__patient=patient).order_by("pk").values_list("pk", flat=True)
        )
        return {
            "id": patient.pk,
            "is_archived": patient.is_archived,
            "appointment_ids": appointment_ids,
            "appointments": list(
                Appointment.objects.filter(patient=patient).order_by("pk").values(
                    "id", "appointment_date", "start_time", "status", "planned_service_id", "doctor_id"
                )
            ),
            "visit_ids": visit_ids,
            "audiometry_exam_ids": list(
                AudiometryExam.objects.filter(visit__appointment__patient=patient)
                .order_by("pk").values_list("pk", flat=True)
            ),
            "provided_service_ids": list(
                ProvidedService.objects.filter(visit__appointment__patient=patient)
                .order_by("pk").values_list("pk", flat=True)
            ),
            "payment_ids": list(
                Payment.objects.filter(visit__appointment__patient=patient)
                .order_by("pk").values_list("pk", flat=True)
            ),
            "external_request_ids": list(
                ExternalBookingRequest.objects.filter(patient=patient)
                .order_by("pk").values_list("pk", flat=True)
            ),
        }
