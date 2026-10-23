from django.db import models
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
    city = models.CharField("Город", max_length=100)
    street = models.CharField("Улица", max_length=150)
    house = models.CharField("Дом", max_length=20)
    apartment = models.CharField("Квартира", max_length=20, blank=True)
    note = models.TextField("Служебное примечание", blank=True)
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
        parts = [self.city, self.street, f"д. {self.house}"]
        if self.apartment:
            parts.append(f"кв. {self.apartment}")
        return ", ".join(parts)

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        if self.birth_date and self.birth_date > timezone.localdate():
            from django.core.exceptions import ValidationError
            raise ValidationError({"birth_date": "Дата рождения не может быть в будущем."})
