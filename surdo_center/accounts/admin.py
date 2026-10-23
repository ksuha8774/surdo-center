from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Роль в АСУ", {"fields": ("middle_name", "role", "specialization")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Роль в АСУ", {"fields": ("first_name", "last_name", "middle_name", "role", "specialization")}),)
    list_display = ("username", "full_name", "role", "is_active")
