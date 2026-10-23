from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Doctor, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Роль в АСУ", {"fields": ("middle_name", "role")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Роль в АСУ", {"fields": ("first_name", "last_name", "middle_name", "role")}),)
    list_display = ("username", "full_name", "role", "is_active")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialization", "is_active")
    search_fields = ("user__last_name", "user__first_name", "user__username")
