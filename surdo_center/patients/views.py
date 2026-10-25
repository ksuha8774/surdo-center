from datetime import date
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required

from .forms import PatientArchiveForm, PatientForm
from .models import Patient
from .services import (
    archive_patient,
    find_exact_duplicate,
    find_possible_duplicates,
    normalize_phone_for_search,
    restore_patient,
)


PATIENT_SCOPES = {"active", "archived", "all"}


def _patient_list_url(request):
    candidate = request.GET.get("return_to") or request.POST.get("return_to")
    default = reverse("patients:list")
    if not candidate:
        return default
    if not url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return default
    if urlsplit(candidate).path != default:
        return default
    return candidate

@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def patient_list(request):
    query = request.GET.get("q", "").strip()
    scope = request.GET.get("scope", "active")
    if scope not in PATIENT_SCOPES:
        scope = "active"
    patients = Patient.objects.all()
    if scope == "active":
        patients = patients.filter(is_archived=False)
    elif scope == "archived":
        patients = patients.filter(is_archived=True)
    if query:
        patients = patients.filter(
            Q(last_name__icontains=query)
            | Q(first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(request, "patients/patient_list.html", {
        "patients": patients,
        "query": query,
        "selected_scope": scope,
    })


@role_required(User.Role.ADMINISTRATOR)
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save()
        messages.success(request, "Карточка пациента создана.")
        return redirect("patients:detail", pk=patient.pk)
    return render(request, "patients/patient_form.html", {
        "form": form,
        "title": "Новый пациент",
        "cancel_url": reverse("patients:list"),
    })


@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    today = timezone.localdate()
    appointments = patient.appointments.select_related("doctor", "planned_service")
    past_appointments = appointments.filter(appointment_date__lt=today).order_by(
        "-appointment_date", "-start_time"
    )
    future_appointments = appointments.filter(appointment_date__gte=today).order_by(
        "appointment_date", "start_time"
    )
    return render(
        request,
        "patients/patient_detail.html",
        {
            "patient": patient,
            "past_appointments": past_appointments,
            "future_appointments": future_appointments,
            "archive_form": PatientArchiveForm(),
            "patient_list_url": _patient_list_url(request),
        },
    )


@role_required(User.Role.ADMINISTRATOR)
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    list_url = _patient_list_url(request)
    detail_url = f"{reverse('patients:detail', args=(pk,))}?{urlencode({'return_to': list_url})}"
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Карточка пациента обновлена.")
        return redirect(detail_url)
    return render(
        request,
        "patients/patient_form.html",
        {
            "form": form,
            "patient": patient,
            "title": "Редактирование пациента",
            "cancel_url": detail_url,
        },
    )


@role_required(User.Role.ADMINISTRATOR)
@require_POST
def patient_archive(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = PatientArchiveForm(request.POST)
    list_url = _patient_list_url(request)
    if not form.is_valid():
        messages.error(request, "Причина архивирования слишком длинная.")
    else:
        try:
            patient, changed = archive_patient(
                patient=patient,
                actor=request.user,
                reason=form.cleaned_data["archive_reason"],
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            if changed:
                messages.success(request, "Карточка пациента перемещена в архив.")
            else:
                messages.info(request, "Карточка пациента уже находится в архиве.")
    detail_url = reverse("patients:detail", args=(pk,))
    return redirect(f"{detail_url}?{urlencode({'return_to': list_url})}")


@role_required(User.Role.ADMINISTRATOR)
@require_POST
def patient_restore(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    list_url = _patient_list_url(request)
    patient, changed = restore_patient(patient=patient, actor=request.user)
    if changed:
        messages.success(request, "Карточка пациента восстановлена и снова доступна для записи.")
    else:
        messages.info(request, "Карточка пациента уже активна.")
    detail_url = reverse("patients:detail", args=(pk,))
    return redirect(f"{detail_url}?{urlencode({'return_to': list_url})}")

@role_required(User.Role.ADMINISTRATOR)
@require_POST
@never_cache
def patient_duplicates(request):
    last_name = request.POST.get("last_name", "").strip()
    first_name = request.POST.get("first_name", "").strip()
    middle_name = request.POST.get("middle_name", "").strip()
    phone = request.POST.get("phone", "")

    birth_date = None
    raw_birth_date = request.POST.get("birth_date", "")

    if raw_birth_date:
        try:
            birth_date = date.fromisoformat(raw_birth_date)
        except ValueError:
            pass

    exclude_pk = request.POST.get("patient_id")

    if not exclude_pk or not exclude_pk.isdigit():
        exclude_pk = None

    params = {
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "birth_date": birth_date,
        "phone": phone,
        "exclude_pk": exclude_pk,
    }

    patients = list(find_possible_duplicates(**params))
    exact = find_exact_duplicate(**params)

    # Гарантируем, что полный дубль попадёт в результаты,
    # даже если он не вошёл в первые пять похожих карточек.
    if exact and not any(p.pk == exact.pk for p in patients):
        patients = [exact] + patients[:4]

    normalized_phone = normalize_phone_for_search(phone)
    results = []

    for patient in patients:
        same_birth_date = (
            birth_date is not None
            and patient.birth_date == birth_date
        )

        same_phone = (
            normalized_phone is not None
            and patient.phone == normalized_phone
        )

        results.append({
            "id": patient.pk,
            "full_name": patient.full_name,
            "birth_date": patient.birth_date.strftime("%d.%m.%Y"),
            "phone": patient.phone,
            "city": patient.city,
            "same_birth_date": same_birth_date,
            "same_phone": same_phone,
            "url": reverse("patients:detail", args=[patient.pk],),
            "is_exact_duplicate": bool(exact and patient.pk == exact.pk),
            "is_archived": patient.is_archived,
        })

    return JsonResponse({"patients": results})
