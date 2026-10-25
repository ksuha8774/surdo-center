import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from .models import Patient


UNFINISHED_APPOINTMENT_STATUSES = ("planned", "in_progress")


def _check_archive_permission(actor):
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Для изменения статуса пациента необходимо войти в систему.")
    if not (actor.is_superuser or actor.role == User.Role.ADMINISTRATOR):
        raise PermissionDenied("Архивировать и восстанавливать пациентов может только регистратор или технический администратор.")


@transaction.atomic
def archive_patient(*, patient, actor, reason=""):
    """Архивирует карточку, сохраняя все связанные записи и медицинские данные."""
    _check_archive_permission(actor)
    locked = Patient.objects.select_for_update().get(pk=patient.pk)
    if locked.is_archived:
        return locked, False

    if locked.appointments.select_for_update().filter(status__in=UNFINISHED_APPOINTMENT_STATUSES).exists():
        raise ValidationError(
            "Нельзя архивировать пациента: у него есть незавершённая запись на приём. "
            "Сначала завершите или отмените запись."
        )

    locked.is_archived = True
    locked.archived_at = timezone.now()
    locked.archived_by = actor
    locked.archive_reason = (reason or "").strip()
    locked.save(update_fields=("is_archived", "archived_at", "archived_by", "archive_reason", "updated_at"))
    return locked, True


@transaction.atomic
def restore_patient(*, patient, actor):
    """Возвращает карточку в активную картотеку; повторный вызов безопасен."""
    _check_archive_permission(actor)
    locked = Patient.objects.select_for_update().get(pk=patient.pk)
    if not locked.is_archived:
        return locked, False

    locked.is_archived = False
    locked.archived_at = None
    locked.archived_by = None
    locked.archive_reason = ""
    locked.save(update_fields=("is_archived", "archived_at", "archived_by", "archive_reason", "updated_at"))
    return locked, True


def normalize_phone_for_search(value):
    value = (value or "").strip()

    if not value or not re.fullmatch(r"\+?[\d\s()\-]+", value):
        return None

    digits = re.sub(r"\D", "", value)

    # Международный номер с кодом страны
    if value.startswith("+"):
        if not 8 <= len(digits) <= 15:
            return None

        if digits.startswith("0"):
            return None

        if digits.startswith("7") and len(digits) != 11:
            return None

        return "+" + digits

    # Российский номер из 10 цифр
    if len(digits) == 10:
        return "+7" + digits

    # Российский номер из 11 цифр, начинающийся с 7 или 8
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return "+7" + digits[1:]

    return None


def find_possible_duplicates(
    last_name,
    first_name,
    middle_name,
    birth_date,
    phone,
    exclude_pk=None,
):
    if not last_name or not first_name:
        return Patient.objects.none()

    normalized_phone = normalize_phone_for_search(phone)

    if not birth_date and not normalized_phone:
        return Patient.objects.none()

    name_filter = Q(
        last_name__iexact=last_name.strip(),
        first_name__iexact=first_name.strip(),
    )

    if middle_name and middle_name.strip():
        name_filter &= Q(
            middle_name__iexact=middle_name.strip()
        )

    match_filter = Q()

    if birth_date:
        match_filter |= Q(birth_date=birth_date)

    if normalized_phone:
        match_filter |= Q(phone=normalized_phone)

    patients = Patient.objects.filter(
        name_filter & match_filter
    )

    if exclude_pk:
        patients = patients.exclude(pk=exclude_pk)

    return patients.order_by("id")[:5]

def find_exact_duplicate(
    last_name,
    first_name,
    middle_name,
    birth_date,
    phone,
    exclude_pk=None,
):
    normalized_phone = normalize_phone_for_search(phone)

    if not all((
        last_name,
        first_name,
        birth_date,
        normalized_phone,
    )):
        return None

    patients = Patient.objects.filter(
        last_name__iexact=last_name.strip(),
        first_name__iexact=first_name.strip(),
        middle_name__iexact=(middle_name or "").strip(),
        birth_date=birth_date,
        phone=normalized_phone,
    )

    if exclude_pk is not None:
        patients = patients.exclude(pk=exclude_pk)

    return patients.first()
