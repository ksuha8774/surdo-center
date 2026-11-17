from django.db import models


class MedicalVisit(models.Model):
    form_type = models.CharField("Тип формы документа", max_length=40, blank=True)
    form_version = models.PositiveSmallIntegerField("Версия формы документа", default=1)
    form_snapshot = models.JSONField("Снимок конфигурации", default=dict, blank=True)
    additional_data = models.JSONField("Дополнительные поля", default=dict, blank=True)
    appointment = models.OneToOneField("scheduling.Appointment", on_delete=models.PROTECT, related_name="visit")
    complaints = models.TextField("Жалобы", blank=True)
    anamnesis = models.TextField("Анамнез", blank=True)
    examination_result = models.TextField("Результаты осмотра", blank=True)
    conclusion = models.TextField("Заключение", blank=True)
    recommendations = models.TextField("Рекомендации", blank=True)
    started_at = models.DateTimeField("Начат", auto_now_add=True)
    completed_at = models.DateTimeField("Завершён", null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(completed_at__isnull=True) | models.Q(completed_at__gte=models.F("started_at")),
                name="medical_visit_completion_order",
            ),
        ]

    def __str__(self):
        return f"Приём: {self.appointment}"

    @property
    def document_fields(self):
        from .configurations import visit_configuration
        config = visit_configuration(self)
        result = []
        used = set()
        for section in config["sections"]:
            for spec in section["fields"]:
                used.add(spec["name"])
                value = getattr(self, spec["name"], self.additional_data.get(spec["name"], ""))
                if value:
                    result.append({"label": spec["label"], "value": value})
        # Preserve visibility of old values even when a later form omits a field.
        for name in ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations"):
            if name not in used and getattr(self, name):
                result.append({"label": self._meta.get_field(name).verbose_name, "value": getattr(self, name)})
        return result
