from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Doctor, User
from .forms import EmployeeCreationForm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Роль в АСУ", {"fields": ("middle_name", "role")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Роль в АСУ", {"fields": ("first_name", "last_name", "middle_name", "role", "specialization")}),)
    list_display = ("username", "full_name", "role", "is_active")
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if not change and obj.role == User.Role.DOCTOR:
            Doctor.objects.create(
                user=obj,
                specialization=form.cleaned_data.get(
                    "specialization", ""
                ),
            )
    def has_delete_permission(self, request, obj=None):
        return False
    add_form = EmployeeCreationForm

    class Media:
        js = ("js/employee_role.js",)


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialization", "is_active")
    search_fields = ("user__last_name", "user__first_name", "user__username")
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if (
            db_field.name == "user"
            and request.resolver_match.url_name == "accounts_doctor_add"
        ):
            kwargs["queryset"] = User.objects.filter(
                role=User.Role.DOCTOR,
                doctor_profile__isnull=True,
            )

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )
    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)

        if obj is not None:
            return (*readonly, "user")

        return readonly
    
    def has_delete_permission(self, request, obj=None):
        return False
