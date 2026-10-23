from django.db import models


class MedicalVisit(models.Model):
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
