import re

from django import forms

from .models import Patient

from .services import (
    find_possible_duplicates,
    find_exact_duplicate,
    normalize_phone_for_search,
)


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = (
            "last_name", "first_name", "middle_name", "birth_date", "sex", "phone", "email",
            "city", "street", "house", "apartment", "note",
        )
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    confirm_duplicate = forms.BooleanField(
        required=False,
        label="Совпадения проверены. Это другой пациент.",
    )

    def clean_phone(self):
        value = self.cleaned_data["phone"]

        normalized = normalize_phone_for_search(value)

        if normalized is None:
            raise forms.ValidationError(
                "Введите российский номер из 10–11 цифр "
                "или международный номер с кодом страны, начиная с +."
            )

        return normalized


    def clean(self):
        data = super().clean()

        self.possible_duplicates = []
        self.exact_duplicate = None

        identity_fields = (
            "last_name",
            "first_name",
            "middle_name",
            "birth_date",
            "phone",
        )

        # При редактировании других полей пациента
        # повторная проверка дубликатов не требуется.
        if self.instance.pk and not any(
            field in self.changed_data
            for field in identity_fields
        ):
            return data

        if not all(data.get(field) for field in (
            "last_name",
            "first_name",
            "birth_date",
            "phone",
        )):
            return data

        params = {
            "last_name": data["last_name"],
            "first_name": data["first_name"],
            "middle_name": data.get("middle_name", ""),
            "birth_date": data["birth_date"],
            "phone": data["phone"],
            "exclude_pk": self.instance.pk,
        }

        # 1. Сначала проверяем полное совпадение.
        exact = find_exact_duplicate(**params)

        if exact:
            self.exact_duplicate = exact
            self.possible_duplicates = [exact]

            self.add_error(
                None,
                "Пациент с такими ФИО, датой рождения "
                "и телефоном уже зарегистрирован. "
                "Используйте существующую карточку.",
            )
            return data

        # 2. Затем ищем частичные совпадения.
        self.possible_duplicates = list(
            find_possible_duplicates(**params)
        )

        if (
            self.possible_duplicates
            and not data.get("confirm_duplicate")
        ):
            self.add_error(
                "confirm_duplicate",
                "Проверьте найденных пациентов "
                "и подтвердите создание отдельной карточки.",
            )

        return data
