from django.contrib import admin

from .models import AudiometryCalculation, AudiometryExam, AudiometryMeasurement


admin.site.register(AudiometryExam)
admin.site.register(AudiometryMeasurement)
admin.site.register(AudiometryCalculation)
