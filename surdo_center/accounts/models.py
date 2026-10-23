from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Администратор"
        DOCTOR = "doctor", "Врач-сурдолог"
        DIRECTOR = "director", "Директор"

    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    role = models.CharField("Роль", max_length=20, choices=Role.choices)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=("administrator", "doctor", "director")),
                name="user_role_valid",
            ),
        ]

    @property
    def full_name(self):
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part).strip() or self.username

    def __str__(self):
        return self.full_name


class Doctor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="doctor_profile",
        db_column="doctor_id",
    )
    specialization = models.CharField("Специализация", max_length=120, blank=True)

    @property
    def full_name(self):
        return self.user.full_name

    @property
    def first_name(self):
        return self.user.first_name

    @property
    def last_name(self):
        return self.user.last_name

    @property
    def is_active(self):
        return self.user.is_active

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != User.Role.DOCTOR:
            from django.core.exceptions import ValidationError
            raise ValidationError({"user": "Профиль врача можно связать только с пользователем роли «Врач»."})
