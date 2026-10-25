import hashlib
import re
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import CharField, F, Func, Q, Value
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from accounts.models import User
from .models import Patient, PatientArchiveEvent


class DuplicatePatientError(ValidationError):
    def __init__(self, patient):
        self.patient = patient
        guidance = (
            "Карточка находится в архиве — восстановите её, а не создавайте новую."
            if patient.is_archived
            else "Используйте существующую карточку."
        )
        super().__init__(
            "Пациент с такими ФИО, датой рождения и телефоном уже зарегистрирован. "
            + guidance
        )


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

    from scheduling.models import Appointment

    unfinished_statuses = (Appointment.Status.PLANNED, Appointment.Status.IN_PROGRESS)
    if locked.appointments.select_for_update().filter(status__in=unfinished_statuses).exists():
        raise ValidationError(
            "Нельзя архивировать пациента: у него есть незавершённая запись на приём. "
            "Сначала завершите или отмените запись."
        )

    locked.is_archived = True
    locked.archived_at = timezone.now()
    locked.archived_by = actor
    locked.archive_reason = (reason or "").strip()
    locked.save(update_fields=("is_archived", "archived_at", "archived_by", "archive_reason", "updated_at"))
    PatientArchiveEvent.objects.create(
        patient=locked,
        action=PatientArchiveEvent.Action.ARCHIVED,
        performed_by=actor,
        reason=locked.archive_reason,
    )
    return locked, True


@transaction.atomic
def restore_patient(*, patient, actor, reason=""):
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
    PatientArchiveEvent.objects.create(
        patient=locked,
        action=PatientArchiveEvent.Action.RESTORED,
        performed_by=actor,
        reason=(reason or "").strip(),
    )
    return locked, True


def normalize_name_part(value):
    return " ".join((value or "").split()).lower()


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


def phones_match(left, right):
    left_normalized = normalize_phone_for_search(left)
    right_normalized = normalize_phone_for_search(right)
    return bool(left_normalized and right_normalized and left_normalized == right_normalized)


def search_patients(queryset, query):
    query = " ".join((query or "").split())
    if not query:
        return queryset

    if re.fullmatch(r"\+?[\d\s()\-]+", query):
        digits = re.sub(r"\D", "", query)
        if not digits:
            return queryset.none()
        # Для российского номера сравниваем национальные 10 цифр: так старые
        # значения, начинающиеся с 8, находятся вместе с каноническими +7.
        if len(digits) > 1 and (
            digits[0] == "8"
            or query.startswith("+7")
            or (len(digits) == 11 and digits[0] == "7")
        ):
            needle = digits[1:]
        else:
            needle = digits
        return queryset.annotate(
            _phone_digits=Func(
                F("phone"),
                Value(r"\D"),
                Value(""),
                Value("g"),
                function="REGEXP_REPLACE",
                output_field=CharField(),
            )
        ).filter(_phone_digits__icontains=needle)

    for token in query.split():
        queryset = queryset.filter(
            Q(last_name__icontains=token)
            | Q(first_name__icontains=token)
            | Q(middle_name__icontains=token)
        )
    return queryset


def _patients_with_same_name(last_name, first_name, middle_name, exclude_pk=None):
    target = tuple(normalize_name_part(value) for value in (last_name, first_name, middle_name))
    normalized = lambda field: Lower(Func(
        Trim(F(field)),
        Value(r"\s+"),
        Value(" "),
        Value("g"),
        function="REGEXP_REPLACE",
        output_field=CharField(),
    ))
    patients = Patient.objects.annotate(
        _normalized_last_name=normalized("last_name"),
        _normalized_first_name=normalized("first_name"),
        _normalized_middle_name=normalized("middle_name"),
    ).filter(
        _normalized_last_name=target[0],
        _normalized_first_name=target[1],
        _normalized_middle_name=target[2],
    ).order_by("id")
    if exclude_pk is not None:
        patients = patients.exclude(pk=exclude_pk)
    return patients


def find_possible_duplicates(
    last_name,
    first_name,
    middle_name,
    birth_date,
    phone,
    exclude_pk=None,
):
    if not last_name or not first_name:
        return []

    normalized_phone = normalize_phone_for_search(phone)

    if not birth_date and not normalized_phone:
        return []

    matches = []
    for patient in _patients_with_same_name(last_name, first_name, middle_name, exclude_pk):
        same_birth_date = bool(birth_date and patient.birth_date == birth_date)
        same_phone = bool(normalized_phone and phones_match(patient.phone, normalized_phone))
        if same_birth_date or same_phone:
            matches.append(patient)
        if len(matches) == 5:
            break
    return matches

def find_exact_duplicate(
    last_name,
    first_name,
    middle_name,
    birth_date,
    phone,
    exclude_pk=None,
):
    normalized_phone = normalize_phone_for_search(phone)
    if isinstance(birth_date, str):
        try:
            birth_date = date.fromisoformat(birth_date)
        except ValueError:
            return None

    if not all((
        last_name,
        first_name,
        birth_date,
        normalized_phone,
    )):
        return None

    for patient in _patients_with_same_name(last_name, first_name, middle_name, exclude_pk):
        if patient.birth_date == birth_date and phones_match(patient.phone, normalized_phone):
            return patient
    return None


def _identity_lock_key(data):
    normalized_phone = normalize_phone_for_search(data.get("phone")) or ""
    parts = [normalize_name_part(data.get(field)) for field in ("last_name", "first_name", "middle_name")]
    parts.extend((str(data.get("birth_date") or ""), normalized_phone))
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def guard_patient_identity(patient):
    data = {
        "last_name": patient.last_name,
        "first_name": patient.first_name,
        "middle_name": patient.middle_name,
        "birth_date": patient.birth_date,
        "phone": patient.phone,
    }
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_identity_lock_key(data)])
    duplicate = find_exact_duplicate(exclude_pk=patient.pk, **data)
    if duplicate:
        raise DuplicatePatientError(duplicate)


@transaction.atomic
def save_patient_form(form):
    """Повторно проверяет полный дубль под PostgreSQL advisory lock и сохраняет форму."""
    try:
        with transaction.atomic():
            return form.save()
    except IntegrityError:
        duplicate = find_exact_duplicate(
            last_name=form.cleaned_data["last_name"],
            first_name=form.cleaned_data["first_name"],
            middle_name=form.cleaned_data.get("middle_name", ""),
            birth_date=form.cleaned_data["birth_date"],
            phone=form.cleaned_data["phone"],
            exclude_pk=form.instance.pk,
        )
        if duplicate:
            raise DuplicatePatientError(duplicate)
        raise
