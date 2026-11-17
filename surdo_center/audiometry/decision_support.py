import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .calculations import CALCULATION_VERSION, calculate_exam, measurement_snapshot
from .models import DecisionAnalysis, DecisionRule, DecisionRuleHit, DecisionRuleSet


OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "between", "exists", "missing"}


def _resolve(values, path):
    current = values
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _compare(actual, operator, expected=None):
    if operator == "exists":
        return actual is not None
    if operator == "missing":
        return actual is None
    if actual is None:
        return False
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "between":
        return expected[0] <= actual <= expected[1]
    raise ValidationError(f"Неизвестный оператор правила: {operator}.")


def validate_condition(condition):
    if not isinstance(condition, dict) or not condition:
        raise ValidationError("Условие правила должно быть непустым объектом.")
    logical = [key for key in ("all", "any", "not") if key in condition]
    if logical:
        if len(logical) != 1 or len(condition) != 1:
            raise ValidationError("Логический узел должен содержать только all, any или not.")
        key = logical[0]
        children = condition[key]
        if key in ("all", "any"):
            if not isinstance(children, list) or not children:
                raise ValidationError(f"Оператор {key} требует непустой список условий.")
            for child in children:
                validate_condition(child)
        else:
            validate_condition(children)
        return
    metric = condition.get("metric")
    operator = condition.get("operator")
    if not isinstance(metric, str) or not metric:
        raise ValidationError("В простом условии укажите metric.")
    if operator not in OPERATORS:
        raise ValidationError("В простом условии указан неподдерживаемый operator.")
    if operator not in ("exists", "missing") and "value" not in condition:
        raise ValidationError("Для сравнения укажите value.")
    if operator == "between" and (
        not isinstance(condition.get("value"), list) or len(condition["value"]) != 2
    ):
        raise ValidationError("Оператор between требует два значения.")


@dataclass(frozen=True)
class RuleEvaluation:
    matched: bool
    evidence: list
    explanation: str


def evaluate_condition(condition, values):
    validate_condition(condition)
    if "all" in condition:
        results = [evaluate_condition(child, values) for child in condition["all"]]
        return RuleEvaluation(
            matched=all(item.matched for item in results),
            evidence=[entry for item in results for entry in item.evidence],
            explanation="; ".join(item.explanation for item in results),
        )
    if "any" in condition:
        results = [evaluate_condition(child, values) for child in condition["any"]]
        matched = [item for item in results if item.matched]
        used = matched or results
        return RuleEvaluation(
            matched=bool(matched),
            evidence=[entry for item in used for entry in item.evidence],
            explanation="; ".join(item.explanation for item in used),
        )
    if "not" in condition:
        result = evaluate_condition(condition["not"], values)
        return RuleEvaluation(
            matched=not result.matched,
            evidence=result.evidence,
            explanation=f"НЕ ({result.explanation})",
        )

    metric = condition["metric"]
    operator = condition["operator"]
    expected = condition.get("value")
    actual = _resolve(values, metric)
    matched = _compare(actual, operator, expected)
    symbols = {"eq": "=", "ne": "≠", "gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
    if operator == "between":
        expression = f"между {expected[0]} и {expected[1]}"
    elif operator == "exists":
        expression = "заполнено"
    elif operator == "missing":
        expression = "не рассчитано"
    else:
        expression = f"{symbols[operator]} {expected}"
    explanation = f"{metric}: фактическое значение {actual if actual is not None else 'отсутствует'}, условие {expression}"
    return RuleEvaluation(
        matched=matched,
        evidence=[{"metric": metric, "actual": actual, "operator": operator, "expected": expected}],
        explanation=explanation,
    )


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError


@transaction.atomic
def run_decision_analysis(exam, performed_by, rule_set=None):
    calculation, indicators = calculate_exam(exam)
    values = indicators.as_dict()
    snapshot = measurement_snapshot(exam.measurements.all())
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    data_hash = hashlib.sha256(encoded).hexdigest()
    warnings = list(indicators.warnings)

    if exam.reliability == exam.Reliability.UNRELIABLE:
        warnings.append("Общая достоверность обследования отмечена врачом как недостоверная.")
    elif exam.reliability == exam.Reliability.LIMITED:
        warnings.append("Общая достоверность обследования ограничена.")
    questionable_count = exam.measurements.filter(reliability="questionable").count()
    if questionable_count:
        warnings.append(f"Измерений с сомнительной достоверностью: {questionable_count}.")

    if rule_set is None:
        rule_set = DecisionRuleSet.objects.filter(is_active=True).order_by("-created_at", "-pk").first()
    if rule_set is None:
        warnings.append("Активный утверждённый набор клинических правил не настроен. Выполнены только количественные расчёты.")
        rules = []
    else:
        if rule_set.is_test:
            warnings.append("Использован тестовый набор правил. Результаты не являются утверждённым клиническим заключением.")
        rules = rule_set.rules.filter(is_active=True)

    analysis = DecisionAnalysis.objects.create(
        exam=exam,
        rule_set=rule_set,
        performed_by=performed_by,
        calculation_version=CALCULATION_VERSION,
        source_updated_at=calculation.source_updated_at,
        input_snapshot=snapshot,
        calculated_values=values,
        data_hash=data_hash,
        warnings=warnings,
    )
    conclusions = []
    recommendations = []
    for rule in rules:
        evaluation = evaluate_condition(rule.condition, values)
        if not evaluation.matched:
            continue
        DecisionRuleHit.objects.create(
            analysis=analysis,
            rule=rule,
            evidence=evaluation.evidence,
            explanation=evaluation.explanation,
            result_text=rule.result_text,
            recommendation_text=rule.recommendation_text,
        )
        conclusions.append(rule.result_text)
        if rule.recommendation_text and rule.recommendation_text not in recommendations:
            recommendations.append(rule.recommendation_text)

    analysis.preliminary_conclusion = "\n".join(conclusions)
    analysis.recommendations = recommendations
    analysis.save(update_fields=("preliminary_conclusion", "recommendations"))
    return analysis
