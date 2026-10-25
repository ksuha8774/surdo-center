from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class Patient(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "female", "Женский"
        MALE = "male", "Мужской"

    last_name = models.CharField("Фамилия", max_length=100, db_index=True)
    first_name = models.CharField("Имя", max_length=100)
    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    birth_date = models.DateField("Дата рождения")
    sex = models.CharField("Пол", max_length=10, choices=Sex.choices)
    phone = models.CharField("Телефон", max_length=30, db_index=True)
    email = models.EmailField("E-mail", blank=True)
    city = models.CharField("Город", max_length=100, blank=True)
    street = models.CharField("Улица", max_length=150, blank=True)
    house = models.CharField("Дом", max_length=20, blank=True)
    apartment = models.CharField("Квартира", max_length=20, blank=True)
    note = models.TextField("Служебное примечание", blank=True)
    is_archived = models.BooleanField("В архиве", default=False, db_index=True, editable=False)
    archived_at = models.DateTimeField("Дата архивирования", null=True, blank=True, editable=False)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Архивировал",
        on_delete=models.SET_NULL,
        related_name="archived_patients",
        null=True,
        blank=True,
        editable=False,
    )
    archive_reason = models.TextField("Причина архивирования", blank=True, editable=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "middle_name")
        indexes = [models.Index(fields=("last_name", "first_name", "middle_name"))]
        constraints = [models.CheckConstraint(condition=models.Q(sex__in=("female", "male")), name="patient_sex_valid")]

    @property
    def full_name(self):
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def full_address(self):
        parts = [part for part in (self.city, self.street) if part]
        if self.house:
            parts.append(f"д. {self.house}")
        if self.apartment:
            parts.append(f"кв. {self.apartment}")
        return ", ".join(parts) or "Не указан"

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        if self.birth_date and self.birth_date > timezone.localdate():
            from django.core.exceptions import ValidationError
            raise ValidationError({"birth_date": "Дата рождения не может быть в будущем."})

    def save(self, *args, **kwargs):
        identity_fields = {"last_name", "first_name", "middle_name", "birth_date", "phone"}
        update_fields = kwargs.get("update_fields")
        identity_changed = self._state.adding
        if not identity_changed and (update_fields is None or identity_fields.intersection(update_fields)):
            previous = type(self).objects.filter(pk=self.pk).values(*identity_fields).first()
            identity_changed = previous is None or any(
                previous[field] != getattr(self, field)
                for field in identity_fields
            )

        if identity_changed:
            from .services import guard_patient_identity

            with transaction.atomic():
                guard_patient_identity(self)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class PatientArchiveEvent(models.Model):
    class Action(models.TextChoices):
        ARCHIVED = "archived", "Архивирование"
        RESTORED = "restored", "Восстановление"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="archive_events")
    action = models.CharField("Действие", max_length=20, choices=Action.choices)
    performed_at = models.DateTimeField("Дата и время", auto_now_add=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Исполнитель",
        on_delete=models.SET_NULL,
        related_name="patient_archive_events",
        null=True,
        blank=True,
    )
    reason = models.TextField("Причина", blank=True)

    class Meta:
        ordering = ("-performed_at", "-pk")
        indexes = [models.Index(fields=("patient", "performed_at"))]

    def __str__(self):
        return f"{self.get_action_display()}: {self.patient}"
