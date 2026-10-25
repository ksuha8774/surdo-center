from django import forms
from django.utils import timezone

from accounts.models import Doctor
from billing.models import Service
from patients.models import Patient


class ServiceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.service_name} — {obj.duration_minutes} мин."


class AppointmentWizardForm(forms.Form):
    patient = forms.ModelChoiceField(label="Пациент", queryset=Patient.objects.none())
    doctor = forms.ModelChoiceField(label="Врач-сурдолог", queryset=Doctor.objects.none())
    service = ServiceChoiceField(label="Услуга", queryset=Service.objects.none())
    appointment_date = forms.DateField(label="Дата приёма", widget=forms.DateInput(attrs={"type": "date"}))
    comment = forms.CharField(label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Причина обращения или важная информация"}))
    referral_info = forms.CharField(label="Сведения о направлении", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(is_archived=False)
        self.fields["doctor"].queryset = Doctor.objects.filter(user__role="doctor", user__is_active=True).select_related("user").order_by("user__last_name", "user__first_name")
        self.fields["service"].queryset = Service.objects.filter(is_active=True).order_by("service_name")
        self.fields["appointment_date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_appointment_date(self):
        value = self.cleaned_data["appointment_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Нельзя записать пациента на прошедшую дату.")
        return value


class RescheduleForm(forms.Form):
    appointment_date = forms.DateField(label="Новая дата", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["appointment_date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_appointment_date(self):
        value = self.cleaned_data["appointment_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Выберите текущую или будущую дату.")
        return value
