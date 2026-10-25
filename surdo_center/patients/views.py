from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required

from .forms import PatientForm
from .models import Patient

from datetime import date

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from .services import (
    find_possible_duplicates,
    find_exact_duplicate,
    normalize_phone_for_search,
)

from django.urls import reverse

@role_required(User.Role.ADMINISTRATOR, User.Role.DOCTOR, User.Role.DIRECTOR)
def patient_list(request):
    query = request.GET.get("q", "").strip()
    patients = Patient.objects.all()
    if query:
        patients = patients.filter(
            Q(last_name__icontains=query)
            | Q(first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(request, "patients/patient_list.html", {"patients": patients, "query": query})


@role_required(User.Role.ADMINISTRATOR)
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save()
        messages.success(request, "Карточка пациента создана.")
        return redirect("patients:detail", pk=patient.pk)
    return render(request, "patients/patient_form.html", {"form": form, "title": "Новый пациент"})


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
        },
    )


@role_required(User.Role.ADMINISTRATOR)
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Карточка пациента обновлена.")
        return redirect("patients:detail", pk=patient.pk)
    return render(
        request,
        "patients/patient_form.html",
        {"form": form, "patient": patient, "title": "Редактирование пациента"},
    )

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
        })

    return JsonResponse({"patients": results})
