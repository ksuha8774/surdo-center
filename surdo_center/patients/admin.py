from django.contrib import admin

from .models import Patient


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
