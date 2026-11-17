from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .models import AudiometryCalculation, AudiometryMeasurement


CALCULATION_VERSION = "pta-abg-1.0"
PTA3_FREQUENCIES = (500, 1000, 2000)
PTA4_FREQUENCIES = (500, 1000, 2000, 4000)


def _round(value):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _mean(values):
    if any(value is None for value in values):
        return None
    return _round(sum(values, Decimal("0")) / Decimal(len(values)))


def _usable(measurement):
    return measurement is not None and not measurement.no_response and measurement.threshold_db_hl is not None


def _index_measurements(measurements):
    return {
        (item.ear, item.conduction_type, item.frequency_hz, item.masked): item
        for item in measurements
    }


def _preferred_threshold(index, ear, conduction, frequency):
    masked = index.get((ear, conduction, frequency, True))
    if masked is not None:
        return masked.threshold_db_hl if _usable(masked) else None
    plain = index.get((ear, conduction, frequency, False))
    return plain.threshold_db_hl if _usable(plain) else None


def _paired_abg(index, ear, frequency):
    for masked in (True, False):
        air = index.get((ear, AudiometryMeasurement.ConductionType.AIR, frequency, masked))
        bone = index.get((ear, AudiometryMeasurement.ConductionType.BONE, frequency, masked))
        if _usable(air) and _usable(bone):
            return _round(air.threshold_db_hl - bone.threshold_db_hl), masked
    return None, None


@dataclass(frozen=True)
class AudiometryIndicators:
    pta3_right: Decimal | None
    pta3_left: Decimal | None
    pta4_right: Decimal | None
    pta4_left: Decimal | None
    max_abg_right: Decimal | None
    max_abg_left: Decimal | None
    pta4_interaural_difference: Decimal | None
    abg_by_frequency: dict
    completeness: dict
    warnings: list

    def as_dict(self):
        return {
            "pta3_right": _json_number(self.pta3_right),
            "pta3_left": _json_number(self.pta3_left),
            "pta4_right": _json_number(self.pta4_right),
            "pta4_left": _json_number(self.pta4_left),
            "max_abg_right": _json_number(self.max_abg_right),
            "max_abg_left": _json_number(self.max_abg_left),
            "pta4_interaural_difference": _json_number(self.pta4_interaural_difference),
            "abg_by_frequency": self.abg_by_frequency,
            "completeness": self.completeness,
            "warnings": self.warnings,
            "calculation_version": CALCULATION_VERSION,
        }


def _json_number(value):
    return float(value) if value is not None else None


def calculate_indicators(measurements):
    measurements = list(measurements)
    index = _index_measurements(measurements)
    pta = {}
    completeness = {"measurement_count": len(measurements), "ears": {}}
    warnings = []

    for ear in (AudiometryMeasurement.Ear.RIGHT, AudiometryMeasurement.Ear.LEFT):
        ear_key = str(ear)
        pta3_values = [
            _preferred_threshold(index, ear, AudiometryMeasurement.ConductionType.AIR, frequency)
            for frequency in PTA3_FREQUENCIES
        ]
        pta4_values = [
            _preferred_threshold(index, ear, AudiometryMeasurement.ConductionType.AIR, frequency)
            for frequency in PTA4_FREQUENCIES
        ]
        pta[(ear, 3)] = _mean(pta3_values)
        pta[(ear, 4)] = _mean(pta4_values)
        missing_pta3 = [frequency for frequency, value in zip(PTA3_FREQUENCIES, pta3_values) if value is None]
        missing_pta4 = [frequency for frequency, value in zip(PTA4_FREQUENCIES, pta4_values) if value is None]
        completeness["ears"][ear_key] = {
            "pta3_complete": not missing_pta3,
            "pta4_complete": not missing_pta4,
            "missing_pta3_frequencies": missing_pta3,
            "missing_pta4_frequencies": missing_pta4,
        }
        if missing_pta4:
            warnings.append(
                f"Недостаточно данных для PTA4 ({'правое' if ear == AudiometryMeasurement.Ear.RIGHT else 'левое'} ухо): "
                f"нет пригодных порогов на частотах {', '.join(map(str, missing_pta4))} Гц."
            )

    abg_by_frequency = {"right": {}, "left": {}}
    max_abg = {}
    frequencies = sorted({item.frequency_hz for item in measurements})
    for ear in (AudiometryMeasurement.Ear.RIGHT, AudiometryMeasurement.Ear.LEFT):
        ear_key = str(ear)
        values = []
        for frequency in frequencies:
            value, masked = _paired_abg(index, ear, frequency)
            if value is not None:
                abg_by_frequency[ear_key][str(frequency)] = {
                    "value": _json_number(value),
                    "masked": masked,
                }
                values.append(value)
        max_abg[ear] = max(values) if values else None

    right_pta4 = pta[(AudiometryMeasurement.Ear.RIGHT, 4)]
    left_pta4 = pta[(AudiometryMeasurement.Ear.LEFT, 4)]
    interaural = _round(abs(right_pta4 - left_pta4)) if right_pta4 is not None and left_pta4 is not None else None
    if not measurements:
        warnings.append("В обследовании нет сохранённых измерений.")

    return AudiometryIndicators(
        pta3_right=pta[(AudiometryMeasurement.Ear.RIGHT, 3)],
        pta3_left=pta[(AudiometryMeasurement.Ear.LEFT, 3)],
        pta4_right=right_pta4,
        pta4_left=left_pta4,
        max_abg_right=max_abg[AudiometryMeasurement.Ear.RIGHT],
        max_abg_left=max_abg[AudiometryMeasurement.Ear.LEFT],
        pta4_interaural_difference=interaural,
        abg_by_frequency=abg_by_frequency,
        completeness=completeness,
        warnings=warnings,
    )


def calculate_exam(exam):
    indicators = calculate_indicators(exam.measurements.all())
    now = timezone.now()
    calculation, _ = AudiometryCalculation.objects.update_or_create(
        exam=exam,
        defaults={
            "pta3_right": indicators.pta3_right,
            "pta3_left": indicators.pta3_left,
            "pta4_right": indicators.pta4_right,
            "pta4_left": indicators.pta4_left,
            "max_abg_right": indicators.max_abg_right,
            "max_abg_left": indicators.max_abg_left,
            "abg_by_frequency": indicators.abg_by_frequency,
            "pta4_interaural_difference": indicators.pta4_interaural_difference,
            "completeness": indicators.completeness,
            "calculation_version": CALCULATION_VERSION,
            "source_updated_at": exam.updated_at,
            "calculated_at": now,
        },
    )
    return calculation, indicators


def measurement_snapshot(measurements):
    return [
        {
            "ear": item.ear,
            "conduction_type": item.conduction_type,
            "frequency_hz": item.frequency_hz,
            "threshold_db_hl": _json_number(item.threshold_db_hl),
            "masked": item.masked,
            "no_response": item.no_response,
            "no_response_level_db_hl": _json_number(item.no_response_level_db_hl),
            "reliability": item.reliability,
        }
        for item in sorted(
            measurements,
            key=lambda item: (item.ear, item.conduction_type, item.frequency_hz, item.masked),
        )
    ]
