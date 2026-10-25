from django.contrib import admin

from .models import Patient, PatientArchiveEvent


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "birth_date", "phone", "is_archived", "created_at")
    list_filter = ("is_archived",)
    search_fields = ("last_name", "first_name", "middle_name", "phone")
    readonly_fields = ("is_archived", "archived_at", "archived_by", "archive_reason")

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(PatientArchiveEvent)
class PatientArchiveEventAdmin(admin.ModelAdmin):
    list_display = ("patient", "action", "performed_at", "performed_by")
    list_filter = ("action", "performed_at")
    search_fields = ("patient__last_name", "patient__first_name", "patient__phone")
    readonly_fields = ("patient", "action", "performed_at", "performed_by", "reason")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
