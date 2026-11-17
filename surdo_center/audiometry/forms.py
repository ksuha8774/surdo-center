from django import forms
from django.core.exceptions import ValidationError

from .models import (
    AUDIOMETRY_FREQUENCIES,
    AUDIOMETRY_MAX_DB_HL,
    AUDIOMETRY_MIN_DB_HL,
    AudiometryExam,
    AudiometryMeasurement,
)


SERIES = tuple(
    (ear, conduction, masked)
    for ear in (AudiometryMeasurement.Ear.RIGHT, AudiometryMeasurement.Ear.LEFT)
    for conduction in (AudiometryMeasurement.ConductionType.AIR, AudiometryMeasurement.ConductionType.BONE)
    for masked in (False, True)
)


def measurement_prefix(ear, conduction, masked):
    return f"{ear}_{conduction}_{'masked' if masked else 'plain'}"


class AudiometryExamForm(forms.ModelForm):
    class Meta:
        model = AudiometryExam
        fields = (
            "exam_datetime",
            "exam_type",
            "reliability",
            "equipment_model",
            "comment",
            "doctor_conclusion",
            "doctor_recommendations",
        )
        widgets = {
            "exam_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "comment": forms.Textarea(attrs={"rows": 3}),
            "doctor_conclusion": forms.Textarea(attrs={"rows": 4}),
            "doctor_recommendations": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, completing=False, **kwargs):
        self.completing = completing
        super().__init__(*args, **kwargs)
        self.fields["exam_datetime"].input_formats = ("%Y-%m-%dT%H:%M",)

    def clean(self):
        data = super().clean()
        if self.completing and not data.get("doctor_conclusion"):
            self.add_error("doctor_conclusion", "Перед завершением оформите заключение врача.")
        return data


class AudiometryMeasurementGridForm(forms.Form):
    def __init__(self, *args, measurements=(), **kwargs):
        super().__init__(*args, **kwargs)
        existing = {
            (item.ear, item.conduction_type, item.frequency_hz, item.masked): item
            for item in measurements
        }
        for ear, conduction, masked in SERIES:
            prefix = measurement_prefix(ear, conduction, masked)
            reliability = next(
                (
                    item.reliability
                    for key, item in existing.items()
                    if key[0] == ear and key[1] == conduction and key[3] == masked
                ),
                AudiometryMeasurement.Reliability.NOT_ASSESSED,
            )
            self.fields[f"{prefix}_reliability"] = forms.ChoiceField(
                label="Достоверность ряда",
                choices=AudiometryMeasurement.Reliability.choices,
                initial=reliability,
                required=False,
            )
            for frequency in AUDIOMETRY_FREQUENCIES:
                item = existing.get((ear, conduction, frequency, masked))
                base = f"{prefix}_{frequency}"
                self.fields[f"{base}_threshold"] = forms.DecimalField(
                    label=f"{frequency} Гц",
                    min_value=AUDIOMETRY_MIN_DB_HL,
                    max_value=AUDIOMETRY_MAX_DB_HL,
                    decimal_places=1,
                    required=False,
                    initial=item.threshold_db_hl if item and not item.no_response else None,
                    widget=forms.NumberInput(attrs={"step": "5", "inputmode": "decimal"}),
                )
                self.fields[f"{base}_no_response"] = forms.BooleanField(
                    label="Нет ответа",
                    required=False,
                    initial=bool(item and item.no_response),
                )
                self.fields[f"{base}_level"] = forms.DecimalField(
                    label="Уровень предъявления",
                    min_value=AUDIOMETRY_MIN_DB_HL,
                    max_value=AUDIOMETRY_MAX_DB_HL,
                    decimal_places=1,
                    required=False,
                    initial=item.no_response_level_db_hl if item and item.no_response else None,
                    widget=forms.NumberInput(attrs={"step": "5", "inputmode": "decimal"}),
                )

    def clean(self):
        data = super().clean()
        rows = []
        for ear, conduction, masked in SERIES:
            prefix = measurement_prefix(ear, conduction, masked)
            reliability = data.get(f"{prefix}_reliability") or AudiometryMeasurement.Reliability.NOT_ASSESSED
            for frequency in AUDIOMETRY_FREQUENCIES:
                base = f"{prefix}_{frequency}"
                threshold = data.get(f"{base}_threshold")
                no_response = bool(data.get(f"{base}_no_response"))
                level = data.get(f"{base}_level")
                if threshold is None and not no_response and level is None:
                    continue
                if no_response:
                    if threshold is not None:
                        self.add_error(f"{base}_threshold", "При отсутствии ответа порог должен быть пустым.")
                    if level is None:
                        self.add_error(f"{base}_level", "Укажите уровень предъявленного сигнала.")
                else:
                    if threshold is None:
                        self.add_error(f"{base}_threshold", "Укажите порог или отметьте отсутствие ответа.")
                    if level is not None:
                        self.add_error(f"{base}_level", "Уровень предъявления указывается только при отсутствии ответа.")
                rows.append({
                    "ear": ear,
                    "conduction_type": conduction,
                    "frequency_hz": frequency,
                    "threshold_db_hl": None if no_response else threshold,
                    "masked": masked,
                    "no_response": no_response,
                    "no_response_level_db_hl": level if no_response else None,
                    "reliability": reliability,
                })
        if self.errors:
            raise ValidationError("Исправьте ошибки в таблице измерений.")
        data["measurement_rows"] = rows
        return data

    @property
    def measurement_rows(self):
        return self.cleaned_data.get("measurement_rows", []) if self.is_bound and self.is_valid() else []

    def table_rows(self):
        labels = {
            AudiometryMeasurement.Ear.RIGHT: "Правое ухо",
            AudiometryMeasurement.Ear.LEFT: "Левое ухо",
            AudiometryMeasurement.ConductionType.AIR: "Воздушная",
            AudiometryMeasurement.ConductionType.BONE: "Костная",
        }
        result = []
        for ear, conduction, masked in SERIES:
            prefix = measurement_prefix(ear, conduction, masked)
            cells = []
            for frequency in AUDIOMETRY_FREQUENCIES:
                base = f"{prefix}_{frequency}"
                cells.append({
                    "frequency": frequency,
                    "threshold": self[f"{base}_threshold"],
                    "no_response": self[f"{base}_no_response"],
                    "level": self[f"{base}_level"],
                })
            result.append({
                "ear": ear,
                "ear_label": labels[ear],
                "conduction": conduction,
                "conduction_label": labels[conduction],
                "masked": masked,
                "reliability": self[f"{prefix}_reliability"],
                "cells": cells,
            })
        return result
