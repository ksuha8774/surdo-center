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

    def __str__(self):
        return f"Приём: {self.appointment}"
