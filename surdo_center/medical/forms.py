from django import forms

from .models import MedicalVisit


class MedicalVisitForm(forms.ModelForm):
    class Meta:
        model = MedicalVisit
        fields = ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations")
        widgets = {
            "complaints": forms.Textarea(attrs={"rows": 4}),
            "anamnesis": forms.Textarea(attrs={"rows": 4}),
            "examination_result": forms.Textarea(attrs={"rows": 4}),
            "conclusion": forms.Textarea(attrs={"rows": 4}),
            "recommendations": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        data = super().clean()
        if self.data.get("complete") and not data.get("conclusion"):
            self.add_error("conclusion", "Перед завершением приёма заполните заключение.")
        return data
