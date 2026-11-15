from django import forms
from django.utils import timezone

from accounts.models import Doctor
from billing.models import Service
from patients.models import Patient
from .models import DoctorScheduleTemplate


class ServiceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.service_name} — {obj.duration_minutes} мин."


class AppointmentWizardForm(forms.Form):
    patient = forms.ModelChoiceField(label="Пациент", queryset=Patient.objects.none(), empty_label="Выберите пациента")
    doctor = forms.ModelChoiceField(label="Врач", queryset=Doctor.objects.none(), empty_label="Выберите врача")
    service = ServiceChoiceField(label="Услуга", queryset=Service.objects.none(), empty_label="Выберите услугу")
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


class WeeklyScheduleForm(forms.Form):
    STEP_CHOICES = ((10, "10 минут"), (15, "15 минут"), (20, "20 минут"), (30, "30 минут"), (45, "45 минут"), (60, "60 минут"))

    doctor = forms.ModelChoiceField(label="Врач", queryset=Doctor.objects.none())
    weekdays = forms.TypedMultipleChoiceField(
        label="Рабочие дни",
        choices=DoctorScheduleTemplate.WEEKDAYS,
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
    )
    start_time = forms.TimeField(label="Начало работы", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="Окончание работы", widget=forms.TimeInput(attrs={"type": "time"}))
    booking_step_minutes = forms.TypedChoiceField(label="Шаг начала записи", choices=STEP_CHOICES, coerce=int, initial=15)
    valid_from = forms.DateField(label="Действует с", widget=forms.DateInput(attrs={"type": "date"}))
    valid_to = forms.DateField(label="Действует по", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = Doctor.objects.filter(
            user__role="doctor", user__is_active=True,
        ).select_related("user").order_by("user__last_name", "user__first_name")
        if not self.is_bound:
            self.fields["valid_from"].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        valid_from = cleaned.get("valid_from")
        valid_to = cleaned.get("valid_to")
        if start_time and end_time and start_time >= end_time:
            self.add_error("end_time", "Время окончания должно быть позже времени начала.")
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", "Дата окончания должна быть не раньше даты начала.")
        return cleaned


class ScheduleExceptionForm(forms.Form):
    TYPE_DAY_OFF = "day_off"
    TYPE_BREAK = "break"
    TYPE_EXTRA = "extra"
    TYPE_CHOICES = (
        (TYPE_DAY_OFF, "Полный выходной"),
        (TYPE_BREAK, "Перерыв или закрытый интервал"),
        (TYPE_EXTRA, "Дополнительное рабочее время"),
    )

    doctor = forms.ModelChoiceField(label="Врач", queryset=Doctor.objects.none())
    exception_date = forms.DateField(label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    exception_type = forms.ChoiceField(label="Тип изменения", choices=TYPE_CHOICES)
    start_time = forms.TimeField(label="Начало", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="Окончание", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    reason = forms.CharField(label="Комментарий", required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = Doctor.objects.filter(
            user__role="doctor", user__is_active=True,
        ).select_related("user").order_by("user__last_name", "user__first_name")
        self.fields["exception_date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean(self):
        cleaned = super().clean()
        exception_type = cleaned.get("exception_type")
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        if exception_type == self.TYPE_DAY_OFF:
            cleaned["start_time"] = None
            cleaned["end_time"] = None
        elif not start_time or not end_time:
            if not start_time:
                self.add_error("start_time", "Укажите начало интервала.")
            if not end_time:
                self.add_error("end_time", "Укажите окончание интервала.")
        elif start_time >= end_time:
            self.add_error("end_time", "Время окончания должно быть позже времени начала.")
        return cleaned
