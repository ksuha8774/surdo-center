from django.contrib import admin

from .models import Appointment, DoctorScheduleException, DoctorScheduleTemplate


admin.site.register(DoctorScheduleTemplate)
admin.site.register(DoctorScheduleException)
admin.site.register(Appointment)
