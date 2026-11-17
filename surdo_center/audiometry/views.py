from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from medical.models import MedicalVisit
from patients.models import Patient

from .calculations import calculate_exam, calculate_indicators, measurement_snapshot
from .decision_support import run_decision_analysis
from .forms import AudiometryExamForm, AudiometryMeasurementGridForm
from .models import AudiometryExam
from .services import can_edit_exam, ensure_can_view, save_exam


def _exam_queryset():
    return AudiometryExam.objects.select_related(
        "patient", "performed_by__user", "visit__appointment",
    ).prefetch_related("measurements", "analyses__rule_hits__rule", "analyses__rule_set")


def _workspace_context(exam, metadata_form, grid_form, *, creating=False):
    measurements = list(exam.measurements.all()) if exam.pk else []
    indicators = calculate_indicators(measurements)
    analyses = list(exam.analyses.all()) if exam.pk else []
    latest_analysis = analyses[0] if analyses else None
    return {
        "exam": exam,
        "metadata_form": metadata_form,
        "grid_form": grid_form,
        "grid_rows": grid_form.table_rows(),
        "measurements_json": measurement_snapshot(measurements),
        "indicators": indicators,
        "latest_analysis": latest_analysis,
        "analyses": analyses,
        "can_edit": creating or can_edit_exam(metadata_form.request_user, exam),
        "can_analyze": bool(
            exam.pk
            and (metadata_form.request_user.is_superuser or exam.performed_by_id == metadata_form.request_user.id)
        ),
        "creating": creating,
    }


def _bind_forms(request, exam, *, completing=False):
    metadata_form = AudiometryExamForm(
        request.POST or None,
        instance=exam,
        completing=completing,
    )
    metadata_form.request_user = request.user
    grid_form = AudiometryMeasurementGridForm(
        request.POST or None,
        measurements=exam.measurements.all() if exam.pk else (),
    )
    return metadata_form, grid_form


@role_required(User.Role.DOCTOR)
def exam_create_for_patient(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if patient.is_archived:
        raise PermissionDenied("Для архивного пациента нельзя создавать новое обследование.")
    exam = AudiometryExam(patient=patient, performed_by=request.user.doctor_profile)
    completing = request.method == "POST" and request.POST.get("action") == "complete"
    metadata_form, grid_form = _bind_forms(request, exam, completing=completing)
    if request.method == "POST" and metadata_form.is_valid() and grid_form.is_valid():
        try:
            exam = save_exam(
                exam=exam,
                metadata_form=metadata_form,
                measurement_form=grid_form,
                complete=completing,
            )
        except ValidationError as error:
            metadata_form.add_error(None, error)
        else:
            calculate_exam(exam)
            messages.success(request, "Аудиометрическое обследование сохранено.")
            return redirect("audiometry:detail", pk=exam.pk)
    return render(
        request,
        "audiometry/exam_workspace.html",
        _workspace_context(exam, metadata_form, grid_form, creating=True),
    )


@role_required(User.Role.DOCTOR)
@transaction.atomic
def exam_create_for_visit(request, visit_pk):
    visit = get_object_or_404(
        MedicalVisit.objects.select_related("appointment__patient", "appointment__doctor"), pk=visit_pk,
    )
    if not request.user.is_superuser and visit.appointment.doctor_id != request.user.id:
        raise PermissionDenied("Нельзя создать обследование для чужого приёма.")
    # Serialize simultaneous submissions for the same visit without locking nullable joins.
    MedicalVisit.objects.select_for_update().get(pk=visit.pk)
    existing = visit.audiometry_exams.order_by("-created_at", "-pk").first()
    if existing:
        return redirect("audiometry:detail", pk=existing.pk)
    patient = visit.appointment.patient
    if patient.is_archived:
        raise PermissionDenied("Для архивного пациента нельзя создавать новое обследование.")
    exam = AudiometryExam(patient=patient, visit=visit, performed_by=request.user.doctor_profile)
    completing = request.method == "POST" and request.POST.get("action") == "complete"
    metadata_form, grid_form = _bind_forms(request, exam, completing=completing)
    if request.method == "POST" and metadata_form.is_valid() and grid_form.is_valid():
        try:
            exam = save_exam(
                exam=exam,
                metadata_form=metadata_form,
                measurement_form=grid_form,
                complete=completing,
            )
        except ValidationError as error:
            metadata_form.add_error(None, error)
        else:
            calculate_exam(exam)
            messages.success(request, "Аудиометрическое обследование сохранено в истории приёма.")
            return redirect("audiometry:detail", pk=exam.pk)
    return render(
        request,
        "audiometry/exam_workspace.html",
        _workspace_context(exam, metadata_form, grid_form, creating=True),
    )


@role_required(User.Role.DOCTOR)
def exam_detail(request, pk):
    exam = get_object_or_404(_exam_queryset(), pk=pk)
    ensure_can_view(request.user, exam)
    editable = can_edit_exam(request.user, exam)
    completing = request.method == "POST" and request.POST.get("action") == "complete"
    if request.method == "POST" and not editable:
        raise PermissionDenied("Редактирование обследования недоступно.")
    metadata_form, grid_form = _bind_forms(request, exam, completing=completing)
    if request.method == "POST" and metadata_form.is_valid() and grid_form.is_valid():
        try:
            exam = save_exam(
                exam=exam,
                metadata_form=metadata_form,
                measurement_form=grid_form,
                complete=completing,
            )
        except ValidationError as error:
            metadata_form.add_error(None, error)
        else:
            calculate_exam(exam)
            messages.success(
                request,
                "Обследование завершено и сохранено в медицинской истории."
                if completing else "Черновик обследования сохранён.",
            )
            return redirect("audiometry:detail", pk=exam.pk)
    return render(
        request,
        "audiometry/exam_workspace.html",
        _workspace_context(exam, metadata_form, grid_form),
    )


@role_required(User.Role.DOCTOR)
@require_POST
def exam_analyze(request, pk):
    exam = get_object_or_404(_exam_queryset(), pk=pk)
    ensure_can_view(request.user, exam)
    if not request.user.is_superuser and exam.performed_by_id != request.user.id:
        raise PermissionDenied("Анализ может запустить только врач-исполнитель.")
    analysis = run_decision_analysis(exam, request.user.doctor_profile)
    if analysis.rule_set is None:
        messages.warning(request, "Расчёты выполнены. Утверждённый набор клинических правил пока не настроен.")
    else:
        messages.success(request, "Анализ СППР выполнен и сохранён в истории.")
    return redirect(f"{reverse('audiometry:detail', args=(pk,))}#analysis")


@role_required(User.Role.DOCTOR)
def exam_compare(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    exams = list(
        _exam_queryset().filter(patient=patient, status=AudiometryExam.Status.COMPLETED).order_by("-exam_datetime")
    )
    selected_ids = [value for value in (request.GET.get("first"), request.GET.get("second")) if value and value.isdigit()]
    selected = [exam for exam in exams if str(exam.pk) in selected_ids]
    if len(selected) < 2:
        selected = exams[:2]
    comparison = [
        {"exam": exam, "measurements_json": measurement_snapshot(exam.measurements.all())}
        for exam in selected[:2]
    ]
    return render(request, "audiometry/exam_compare.html", {
        "patient": patient,
        "exams": exams,
        "comparison": comparison,
    })
