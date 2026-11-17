from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User

from .models import AudiometryExam, AudiometryMeasurement


def can_view_exam(user, exam):
    return bool(user.is_authenticated and (user.is_superuser or user.role == User.Role.DOCTOR))


def can_edit_exam(user, exam):
    return bool(
        can_view_exam(user, exam)
        and exam.status == AudiometryExam.Status.DRAFT
        and (user.is_superuser or exam.performed_by_id == user.id)
    )


@transaction.atomic
def save_exam(*, exam, metadata_form, measurement_form, complete=False):
    if exam.pk:
        exam = AudiometryExam.objects.select_for_update().get(pk=exam.pk)
        if exam.status == AudiometryExam.Status.COMPLETED:
            raise ValidationError("Завершённое обследование нельзя редактировать.")

    for field, value in metadata_form.cleaned_data.items():
        setattr(exam, field, value)

    rows = measurement_form.cleaned_data["measurement_rows"]
    if complete and not rows:
        raise ValidationError("Нельзя завершить обследование без измерений.")

    if complete:
        exam.status = AudiometryExam.Status.COMPLETED
        exam.completed_at = timezone.now()
    else:
        exam.status = AudiometryExam.Status.DRAFT
        exam.completed_at = None
    exam.full_clean()
    exam.save()

    submitted_keys = set()
    for values in rows:
        key = (
            values["ear"], values["conduction_type"], values["frequency_hz"], values["masked"],
        )
        submitted_keys.add(key)
        measurement = AudiometryMeasurement(exam=exam, **values)
        measurement.full_clean()
        AudiometryMeasurement.objects.update_or_create(
            exam=exam,
            ear=values["ear"],
            conduction_type=values["conduction_type"],
            frequency_hz=values["frequency_hz"],
            masked=values["masked"],
            defaults={
                "threshold_db_hl": values["threshold_db_hl"],
                "no_response": values["no_response"],
                "no_response_level_db_hl": values["no_response_level_db_hl"],
                "reliability": values["reliability"],
            },
        )

    for measurement in exam.measurements.all():
        key = (
            measurement.ear,
            measurement.conduction_type,
            measurement.frequency_hz,
            measurement.masked,
        )
        if key not in submitted_keys:
            measurement.delete()

    exam.updated_at = timezone.now()
    exam.save(update_fields=("updated_at",))
    return exam


def ensure_can_view(user, exam):
    if not can_view_exam(user, exam):
        raise PermissionDenied("Нет доступа к медицинским результатам.")


def ensure_can_edit(user, exam):
    if not can_edit_exam(user, exam):
        raise PermissionDenied("Редактирование этого обследования недоступно.")
