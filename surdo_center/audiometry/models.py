from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


AUDIOMETRY_FREQUENCIES = (125, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 6000, 8000)
AUDIOMETRY_MIN_DB_HL = -10
AUDIOMETRY_MAX_DB_HL = 130


class AudiometryExam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        COMPLETED = "completed", "Завершено"

    class ExamType(models.TextChoices):
        PURE_TONE = "pure_tone", "Тональная пороговая аудиометрия"

    class Reliability(models.TextChoices):
        NOT_ASSESSED = "not_assessed", "Не оценена"
        RELIABLE = "reliable", "Достоверные данные"
        LIMITED = "limited", "Ограниченная достоверность"
        UNRELIABLE = "unreliable", "Недостоверные данные"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="audiometry_exams")
    visit = models.ForeignKey(
        "medical.MedicalVisit", on_delete=models.PROTECT, related_name="audiometry_exams", null=True, blank=True,
    )
    performed_by = models.ForeignKey(
        "accounts.Doctor", on_delete=models.PROTECT, related_name="performed_audiometry_exams",
    )
    exam_datetime = models.DateTimeField("Дата и время обследования", default=timezone.now)
    exam_type = models.CharField(
        "Тип исследования", max_length=30, choices=ExamType.choices, default=ExamType.PURE_TONE,
    )
    status = models.CharField(
        "Статус", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )
    reliability = models.CharField(
        "Общая достоверность", max_length=20, choices=Reliability.choices, default=Reliability.NOT_ASSESSED,
    )
    equipment_model = models.CharField("Модель оборудования", max_length=120, blank=True)
    completed_at = models.DateTimeField("Завершено", null=True, blank=True)
    comment = models.TextField("Примечания", blank=True)
    doctor_conclusion = models.TextField("Заключение врача", blank=True)
    doctor_recommendations = models.TextField("Рекомендации врача", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        ordering = ("-exam_datetime", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("exam_datetime")),
                name="audiometry_exam_completion_order",
            ),
            models.CheckConstraint(
                condition=(Q(status="draft", completed_at__isnull=True) | Q(status="completed", completed_at__isnull=False)),
                name="audiometry_exam_status_consistent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.visit_id:
            appointment = self.visit.appointment
            if self.patient_id and appointment.patient_id != self.patient_id:
                raise ValidationError({"visit": "Приём относится к другому пациенту."})
            if self.performed_by_id and appointment.doctor_id != self.performed_by_id:
                raise ValidationError({"performed_by": "Обследование должен проводить врач этого приёма."})
        if self.status == self.Status.COMPLETED and not self.completed_at:
            raise ValidationError({"completed_at": "Для завершённого обследования укажите время завершения."})
        if self.status == self.Status.DRAFT and self.completed_at:
            raise ValidationError({"completed_at": "У черновика не должно быть времени завершения."})

    def save(self, *args, **kwargs):
        if not self.patient_id and self.visit_id:
            self.patient_id = self.visit.appointment.patient_id
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Аудиометрия {self.patient} от {timezone.localtime(self.exam_datetime):%d.%m.%Y %H:%M}"


class AudiometryMeasurement(models.Model):
    class Ear(models.TextChoices):
        LEFT = "left", "Левое"
        RIGHT = "right", "Правое"

    class ConductionType(models.TextChoices):
        AIR = "air", "Воздушная"
        BONE = "bone", "Костная"

    class Reliability(models.TextChoices):
        NOT_ASSESSED = "not_assessed", "Не оценена"
        RELIABLE = "reliable", "Достоверно"
        QUESTIONABLE = "questionable", "Сомнительно"

    exam = models.ForeignKey(AudiometryExam, on_delete=models.CASCADE, related_name="measurements")
    ear = models.CharField("Ухо", max_length=5, choices=Ear.choices)
    conduction_type = models.CharField("Тип проводимости", max_length=10, choices=ConductionType.choices)
    frequency_hz = models.PositiveIntegerField(
        "Частота, Гц",
        validators=[MinValueValidator(min(AUDIOMETRY_FREQUENCIES)), MaxValueValidator(max(AUDIOMETRY_FREQUENCIES))],
    )
    threshold_db_hl = models.DecimalField(
        "Порог, дБ HL", max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(AUDIOMETRY_MIN_DB_HL), MaxValueValidator(AUDIOMETRY_MAX_DB_HL)],
    )
    masked = models.BooleanField("С маскировкой", default=False)
    no_response = models.BooleanField("Нет ответа", default=False)
    no_response_level_db_hl = models.DecimalField(
        "Уровень предъявления, дБ HL", max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(AUDIOMETRY_MIN_DB_HL), MaxValueValidator(AUDIOMETRY_MAX_DB_HL)],
    )
    reliability = models.CharField(
        "Достоверность", max_length=20, choices=Reliability.choices, default=Reliability.NOT_ASSESSED,
    )

    class Meta:
        ordering = ("exam", "ear", "conduction_type", "frequency_hz", "masked")
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "ear", "conduction_type", "frequency_hz", "masked"),
                name="unique_audiometry_measurement",
            ),
            models.CheckConstraint(
                condition=Q(frequency_hz__in=AUDIOMETRY_FREQUENCIES), name="audiometry_frequency_allowed",
            ),
            models.CheckConstraint(condition=Q(ear__in=("left", "right")), name="audiometry_ear_valid"),
            models.CheckConstraint(condition=Q(conduction_type__in=("air", "bone")), name="audiometry_conduction_valid"),
            models.CheckConstraint(
                condition=(
                    Q(no_response=False, threshold_db_hl__isnull=False, no_response_level_db_hl__isnull=True)
                    | Q(no_response=True, threshold_db_hl__isnull=True, no_response_level_db_hl__isnull=False)
                ),
                name="audiometry_response_values_consistent",
            ),
            models.CheckConstraint(
                condition=Q(threshold_db_hl__isnull=True)
                | Q(threshold_db_hl__range=(AUDIOMETRY_MIN_DB_HL, AUDIOMETRY_MAX_DB_HL)),
                name="audiometry_threshold_in_range",
            ),
            models.CheckConstraint(
                condition=Q(no_response_level_db_hl__isnull=True)
                | Q(no_response_level_db_hl__range=(AUDIOMETRY_MIN_DB_HL, AUDIOMETRY_MAX_DB_HL)),
                name="audiometry_presentation_level_in_range",
            ),
        ]

    def clean(self):
        super().clean()
        if self.frequency_hz not in AUDIOMETRY_FREQUENCIES:
            raise ValidationError({"frequency_hz": "Недопустимая частота аудиометрии."})
        if self.no_response:
            if self.threshold_db_hl is not None:
                raise ValidationError({"threshold_db_hl": "При отсутствии ответа порог не указывается."})
            if self.no_response_level_db_hl is None:
                raise ValidationError({"no_response_level_db_hl": "Укажите уровень предъявленного сигнала."})
        else:
            if self.threshold_db_hl is None:
                raise ValidationError({"threshold_db_hl": "Укажите измеренный порог."})
            if self.no_response_level_db_hl is not None:
                raise ValidationError({"no_response_level_db_hl": "Уровень предъявления указывается только при отсутствии ответа."})


class AudiometryCalculation(models.Model):
    exam = models.OneToOneField(AudiometryExam, on_delete=models.CASCADE, related_name="calculation")
    pta3_right = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pta3_left = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pta4_right = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pta4_left = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    max_abg_right = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    max_abg_left = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    abg_by_frequency = models.JSONField("ВКИ по частотам", default=dict)
    pta4_interaural_difference = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    completeness = models.JSONField("Полнота данных", default=dict)
    calculation_version = models.CharField("Версия расчёта", max_length=30)
    source_updated_at = models.DateTimeField("Версия исходных данных", default=timezone.now)
    calculated_at = models.DateTimeField("Рассчитано", default=timezone.now)


class DecisionRuleSet(models.Model):
    code = models.SlugField("Код набора", max_length=60)
    name = models.CharField("Название", max_length=160)
    version = models.CharField("Версия", max_length=30)
    description = models.TextField("Описание", blank=True)
    is_active = models.BooleanField("Активен", default=False)
    is_test = models.BooleanField("Тестовый набор", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ("code", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("code", "version"), name="unique_decision_rule_set_version"),
            models.UniqueConstraint(fields=("code",), condition=Q(is_active=True), name="unique_active_decision_rule_set"),
        ]

    def __str__(self):
        return f"{self.name} ({self.version})"


class DecisionRule(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Информация"
        WARNING = "warning", "Предупреждение"

    rule_set = models.ForeignKey(DecisionRuleSet, on_delete=models.PROTECT, related_name="rules")
    code = models.SlugField("Код правила", max_length=80)
    title = models.CharField("Название", max_length=180)
    description = models.TextField("Описание", blank=True)
    condition = models.JSONField("Условие")
    result_text = models.TextField("Предварительный вывод")
    recommendation_text = models.TextField("Рекомендация", blank=True)
    severity = models.CharField("Уровень", max_length=20, choices=Severity.choices, default=Severity.INFO)
    priority = models.PositiveSmallIntegerField("Приоритет", default=100)
    is_active = models.BooleanField("Активно", default=True)

    class Meta:
        ordering = ("priority", "code")
        constraints = [
            models.UniqueConstraint(fields=("rule_set", "code"), name="unique_decision_rule_code"),
        ]

    def __str__(self):
        return f"{self.rule_set.version}: {self.title}"


class DecisionAnalysis(models.Model):
    exam = models.ForeignKey(AudiometryExam, on_delete=models.PROTECT, related_name="analyses")
    rule_set = models.ForeignKey(
        DecisionRuleSet, on_delete=models.PROTECT, related_name="analyses", null=True, blank=True,
    )
    performed_by = models.ForeignKey(
        "accounts.Doctor", on_delete=models.PROTECT, related_name="audiometry_analyses",
    )
    calculation_version = models.CharField("Версия расчёта", max_length=30)
    source_updated_at = models.DateTimeField("Версия исходных данных")
    input_snapshot = models.JSONField("Снимок измерений")
    calculated_values = models.JSONField("Рассчитанные показатели")
    data_hash = models.CharField("Контрольная сумма данных", max_length=64)
    preliminary_conclusion = models.TextField("Предварительный вывод", blank=True)
    recommendations = models.JSONField("Рекомендации", default=list)
    warnings = models.JSONField("Предупреждения", default=list)
    created_at = models.DateTimeField("Выполнен", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    @property
    def is_stale(self):
        return self.exam.updated_at > self.source_updated_at


class DecisionRuleHit(models.Model):
    analysis = models.ForeignKey(DecisionAnalysis, on_delete=models.CASCADE, related_name="rule_hits")
    rule = models.ForeignKey(DecisionRule, on_delete=models.PROTECT, related_name="hits")
    evidence = models.JSONField("Доказательные значения")
    explanation = models.TextField("Объяснение")
    result_text = models.TextField("Предварительный вывод")
    recommendation_text = models.TextField("Рекомендация", blank=True)

    class Meta:
        ordering = ("rule__priority", "pk")
        constraints = [
            models.UniqueConstraint(fields=("analysis", "rule"), name="unique_rule_hit_per_analysis"),
        ]
