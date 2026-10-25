import re

from django.db.models import Q

from .models import Patient


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