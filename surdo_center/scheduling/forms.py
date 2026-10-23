from django import forms
from django.utils import timezone

from accounts.models import User
from billing.models import Service
from patients.models import Patient


class AppointmentWizardForm(forms.Form):
    patient = forms.ModelChoiceField(label="Пациент", queryset=Patient.objects.none())
    doctor = forms.ModelChoiceField(label="Врач-сурдолог", queryset=User.objects.none())
    service = forms.ModelChoiceField(label="Услуга", queryset=Service.objects.none())
    appointment_date = forms.DateField(label="Дата приёма", widget=forms.DateInput(attrs={"type": "date"}))
    comment = forms.CharField(label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Причина обращения или важная информация"}))
    referral_info = forms.CharField(label="Сведения о направлении", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.all()
        self.fields["doctor"].queryset = User.objects.filter(role=User.Role.DOCTOR, is_active=True).order_by("last_name", "first_name")
        self.fields["service"].queryset = Service.objects.filter(is_active=True)

    def clean_appointment_date(self):
        value = self.cleaned_data["appointment_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Нельзя записать пациента на прошедшую дату.")
        return value


class RescheduleForm(forms.Form):
    appointment_date = forms.DateField(label="Новая дата", widget=forms.DateInput(attrs={"type": "date"}))

    def clean_appointment_date(self):
        value = self.cleaned_data["appointment_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Выберите текущую или будущую дату.")
        return value
