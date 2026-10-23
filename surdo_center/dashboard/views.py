from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render
from django.utils import timezone

from accounts.models import User
from scheduling.models import Appointment, DoctorScheduleTemplate


@login_required
def dashboard(request):
    today = timezone.localdate()
    appointments = Appointment.objects.filter(appointment_date=today).select_related("patient", "doctor", "planned_service")
    context = {"today": today, "role": request.user.role}

    if request.user.role == User.Role.DOCTOR:
        own = appointments.filter(doctor_id=request.user.pk)
        context.update({
            "today_total": own.count(),
            "today_completed": own.filter(status=Appointment.Status.COMPLETED).count(),
            "today_remaining": own.filter(status__in=(Appointment.Status.PLANNED, Appointment.Status.IN_PROGRESS)).count(),
            "upcoming": own.filter(status__in=(Appointment.Status.PLANNED, Appointment.Status.IN_PROGRESS)).order_by("start_time")[:8],
        })
    elif request.user.role == User.Role.DIRECTOR:
        working_doctors = DoctorScheduleTemplate.objects.filter(
            weekday=today.weekday(), valid_from__lte=today, is_active=True,
        ).filter(models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=today)).values("doctor").distinct().count()
        context.update({
            "today_total": appointments.count(),
            "today_completed": appointments.filter(status=Appointment.Status.COMPLETED).count(),
            "working_doctors": working_doctors,
            "upcoming": appointments.order_by("start_time")[:8],
        })
    else:
        context.update({
            "today_total": appointments.count(),
            "today_remaining": appointments.filter(status=Appointment.Status.PLANNED).count(),
            "today_completed": appointments.filter(status=Appointment.Status.COMPLETED).count(),
            "upcoming": appointments.filter(status__in=(Appointment.Status.PLANNED, Appointment.Status.IN_PROGRESS)).order_by("start_time")[:8],
        })
    return render(request, "dashboard/index.html", context)
