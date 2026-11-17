from django import forms
from django.core.exceptions import ValidationError

from .configurations import visit_configuration
from .models import MedicalVisit


class MedicalVisitForm(forms.ModelForm):
    class Meta:
        model = MedicalVisit
        fields = ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations")

    def __init__(self, *args, configuration=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuration = configuration or visit_configuration(self.instance)
        self.sections = []
        configured = {}
        for section in self.configuration["sections"]:
            names = []
            for spec in section["fields"]:
                name = spec["name"]
                if name.startswith("extra_"):
                    initial = self.instance.additional_data.get(name, "")
                elif name in self.Meta.fields:
                    initial = getattr(self.instance, name)
                else:
                    raise ValidationError("Недопустимое поле медицинской формы.")
                kind = spec.get("kind", "textarea")
                common = dict(label=spec["label"], required=False, initial=initial)
                if kind in ("textarea", "text"):
                    widget = forms.Textarea(attrs={"rows": 3, "placeholder": spec["label"] + "…"}) if kind == "textarea" else forms.TextInput()
                    item = forms.CharField(widget=widget, max_length=spec.get("max_length"), **common)
                elif kind == "date":
                    item = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), **common)
                elif kind == "choice":
                    item = forms.ChoiceField(choices=[("", "Выберите значение")] + [(v, v) for v in spec["choices"]], **common)
                elif kind == "number":
                    item = forms.DecimalField(min_value=spec.get("min_value"), max_value=spec.get("max_value"), **common)
                else:
                    raise ValidationError("Недопустимый тип поля медицинской формы.")
                configured[name] = item
                names.append((name, spec.get("required", False)))
            self.sections.append({"title": section["title"], "names": names})
        self.fields = configured

    @property
    def rendered_sections(self):
        return [{"title": section["title"], "fields": [
            {"bound": self[name], "required": required} for name, required in section["names"]
        ]} for section in self.sections]

    def clean(self):
        data = super().clean()
        if self.data.get("complete"):
            for section in self.sections:
                for name, required in section["names"]:
                    if required and data.get(name) in (None, ""):
                        self.add_error(name, "Перед завершением приёма заполните это поле.")
            if "audiometry" in self.configuration.get("completion_modules", []):
                if not self.instance.audiometry_exams.filter(status="completed").exists():
                    self.add_error(None, "Для завершения требуется завершённое аудиометрическое обследование.")
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        extra = dict(instance.additional_data)
        for name, value in self.cleaned_data.items():
            if name.startswith("extra_"):
                extra[name] = value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else ""
        instance.additional_data = extra
        if commit:
            instance.save()
        return instance
