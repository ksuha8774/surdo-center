from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required

from .forms import PatientForm
from .models import Patient


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
