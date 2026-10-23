from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "birth_date", "phone", "created_at")
    search_fields = ("last_name", "first_name", "middle_name", "phone")
