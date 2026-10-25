from django import forms
from django.contrib.auth.forms import AdminUserCreationForm

from .models import User



class EmployeeCreationForm(AdminUserCreationForm):
    specialization = forms.CharField(
        label="Специализация",
        max_length=120,
        required=False,
        help_text="Заполняется для врача-сурдолога.",
    )

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "middle_name",
            "role",
        )
    def clean(self):
        cleaned_data = super().clean()

        role = cleaned_data.get("role")
        specialization = cleaned_data.get("specialization")

        if role != User.Role.DOCTOR and specialization:
            self.add_error(
                "specialization",
                "Специализацию можно указывать только для врача."
            )

        return cleaned_data