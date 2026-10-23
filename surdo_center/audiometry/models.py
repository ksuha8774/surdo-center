from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class AudiometryExam(models.Model):
    visit = models.ForeignKey("medical.MedicalVisit", on_delete=models.PROTECT, related_name="audiometry_exams")
    performed_by = models.ForeignKey("accounts.Doctor", on_delete=models.PROTECT, related_name="performed_audiometry_exams")
    exam_datetime = models.DateTimeField("Дата и время обследования", default=timezone.now)
    equipment_model = models.CharField("Модель оборудования", max_length=120, blank=True)
    completed_at = models.DateTimeField("Завершено", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        ordering = ("-exam_datetime",)
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("exam_datetime")),
                name="audiometry_exam_completion_order",
            ),
        ]


class AudiometryMeasurement(models.Model):
    class Ear(models.TextChoices):
        LEFT = "left", "Левое"
        RIGHT = "right", "Правое"

    class ConductionType(models.TextChoices):
        AIR = "air", "Воздушная"
        BONE = "bone", "Костная"

    exam = models.ForeignKey(AudiometryExam, on_delete=models.CASCADE, related_name="measurements")
    ear = models.CharField("Ухо", max_length=5, choices=Ear.choices)
    conduction_type = models.CharField("Тип проводимости", max_length=10, choices=ConductionType.choices)
    frequency_hz = models.PositiveIntegerField("Частота, Гц", validators=[MinValueValidator(1)])
    threshold_db_hl = models.DecimalField("Порог, дБ HL", max_digits=5, decimal_places=1, null=True, blank=True)
    masked = models.BooleanField("С маскировкой", default=False)
    no_response = models.BooleanField("Нет ответа", default=False)
    no_response_level_db_hl = models.DecimalField("Уровень без ответа, дБ HL", max_digits=5, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ("exam", "ear", "conduction_type", "frequency_hz", "masked")
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "ear", "conduction_type", "frequency_hz", "masked"),
                name="unique_audiometry_measurement",
            ),
            models.CheckConstraint(condition=Q(frequency_hz__gt=0), name="audiometry_frequency_positive"),
            models.CheckConstraint(condition=Q(ear__in=("left", "right")), name="audiometry_ear_valid"),
            models.CheckConstraint(condition=Q(conduction_type__in=("air", "bone")), name="audiometry_conduction_valid"),
            models.CheckConstraint(
                condition=(
                    Q(no_response=False, threshold_db_hl__isnull=False, no_response_level_db_hl__isnull=True)
                    | Q(no_response=True, threshold_db_hl__isnull=True, no_response_level_db_hl__isnull=False)
                ),
                name="audiometry_response_values_consistent",
            ),
        ]


class AudiometryCalculation(models.Model):
    exam = models.OneToOneField(AudiometryExam, on_delete=models.CASCADE, related_name="calculation")
    pta4_right = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pta4_left = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    max_abg_right = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    max_abg_left = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pta4_interaural_difference = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    calculation_version = models.CharField("Версия расчёта", max_length=30)
    calculated_at = models.DateTimeField("Рассчитано", default=timezone.now)
