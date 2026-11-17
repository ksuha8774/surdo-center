"""Declarative, versioned form definitions. Never modify a published version."""
from copy import deepcopy


def field(name, label, required=False, kind="textarea", **rules):
    return dict(name=name, label=label, required=required, kind=kind, **rules)


def definition(code, title, sections, modules=(), pending=False, completion_modules=()):
    return dict(code=code, version=1, title=title, sections=sections,
                modules=list(modules), pending=pending,
                completion_modules=list(completion_modules))


OUTCOME = [field("conclusion", "Заключение врача", True), field("recommendations", "Рекомендации")]
PRIMARY = [field("complaints", "Жалобы"), field("anamnesis", "Анамнез"),
           field("examination_result", "Результаты осмотра")]
REGISTRY = {}


def register(config):
    REGISTRY[(config["code"], config["version"])] = config


register(definition("primary", "Первичная консультация", [
    dict(title="Данные осмотра", fields=PRIMARY), dict(title="Итоги приёма", fields=OUTCOME)]))
register(definition("repeat", "Повторная консультация", [
    dict(title="Динамика и осмотр", fields=[field("complaints", "Текущие жалобы"),
         field("anamnesis", "Динамика состояния"), field("examination_result", "Результаты осмотра")]),
    dict(title="Итоги приёма", fields=OUTCOME)]))
register(definition("hearing_diagnostic", "Диагностика слуха", [
    dict(title="Итоги обследования", fields=OUTCOME)], modules=("audiometry",)))
register(definition("results", "Консультация по результатам обследования", [
    dict(title="Результаты и интерпретация", fields=[field("complaints", "Причина обращения"),
         field("examination_result", "Интерпретация результатов врачом")]),
    dict(title="Итоги приёма", fields=OUTCOME)], modules=("exam_history",)))
register(definition("brief", "Краткая консультация", [dict(title="Консультация", fields=[
    field("complaints", "Причина обращения"), field("conclusion", "Результат консультации", True),
    field("recommendations", "Рекомендации")])]))
register(definition("extended", "Расширенная консультация", [dict(title="Консультация", fields=[
    field("complaints", "Причина обращения"), field("conclusion", "Результат консультации"),
    field("recommendations", "Рекомендации")])], pending=True))
register(definition("basic", "Базовая форма — требуется согласование", [dict(title="Консультация", fields=[
    field("complaints", "Причина обращения"), field("conclusion", "Результат консультации"),
    field("recommendations", "Рекомендации")])], pending=True))
register(definition("legacy", "Ранее созданная медицинская запись", [
    dict(title="Данные осмотра", fields=PRIMARY), dict(title="Итоги приёма", fields=OUTCOME)],
    modules=("audiometry",)))

FORM_CHOICES = [(code, config["title"]) for (code, version), config in REGISTRY.items() if code != "legacy"]


def get_configuration(code, version=1):
    try:
        return deepcopy(REGISTRY[(code, version)])
    except KeyError:
        from django.core.exceptions import ValidationError
        raise ValidationError("Неизвестная версия медицинской формы. Проверьте назначение услуги.")


def visit_configuration(visit):
    if visit.form_snapshot:
        return deepcopy(visit.form_snapshot)
    service = visit.appointment.planned_service
    return get_configuration(service.medical_form_type, service.medical_form_version)
