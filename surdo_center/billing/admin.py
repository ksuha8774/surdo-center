from django.contrib import admin

from .models import Payment, ProvidedService, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("service_name", "medical_form_type", "medical_form_version", "is_active")
    list_filter = ("medical_form_type", "is_active")
admin.site.register(ProvidedService)
admin.site.register(Payment)
