import re

from django import forms

from .models import Patient


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = (
            "last_name", "first_name", "middle_name", "birth_date", "sex", "phone", "email",
            "city", "street", "house", "apartment", "note",
        )
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_phone(self):
        value = self.cleaned_data["phone"].strip()
        digits = re.sub(r"\D", "", value)
        if len(digits) not in (10, 11):
            raise forms.ValidationError("Введите телефон из 10–11 цифр.")
        normalized = "+7" + digits[-10:]
        duplicate = Patient.objects.filter(phone=normalized).exclude(pk=self.instance.pk).first()
        if duplicate:
            raise forms.ValidationError(f"Пациент с этим телефоном уже существует: {duplicate.full_name}.")
        return normalized

    def clean(self):
        data = super().clean()
        required = ("last_name", "first_name", "birth_date")
        if all(data.get(field) for field in required):
            duplicate = Patient.objects.filter(
                last_name__iexact=data["last_name"],
                first_name__iexact=data["first_name"],
                middle_name__iexact=data.get("middle_name", ""),
                birth_date=data["birth_date"],
            ).exclude(pk=self.instance.pk).first()
            if duplicate:
                raise forms.ValidationError("Найден возможный дубль: пациент с таким ФИО и датой рождения уже существует.")
        return data
