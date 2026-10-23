from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Администратор"
        DOCTOR = "doctor", "Врач-сурдолог"
        DIRECTOR = "director", "Директор"

    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    role = models.CharField("Роль", max_length=20, choices=Role.choices)
    specialization = models.CharField("Специализация", max_length=120, blank=True)

    @property
    def full_name(self):
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part).strip() or self.username

    def __str__(self):
        return self.full_name
