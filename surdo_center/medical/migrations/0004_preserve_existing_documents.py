from django.db import migrations


def preserve(apps, schema_editor):
    Visit = apps.get_model("medical", "MedicalVisit")
    # Frozen legacy layout keeps every existing field and its original meaning.
    snapshot = {
        "code": "legacy", "version": 1, "title": "Ранее созданная медицинская запись",
        "modules": ["audiometry"], "completion_modules": [], "pending": False,
        "sections": [
            {"title": "Данные осмотра", "fields": [
                {"name": "complaints", "label": "Жалобы", "kind": "textarea", "required": False},
                {"name": "anamnesis", "label": "Анамнез", "kind": "textarea", "required": False},
                {"name": "examination_result", "label": "Результаты осмотра", "kind": "textarea", "required": False},
            ]},
            {"title": "Итоги приёма", "fields": [
                {"name": "conclusion", "label": "Заключение врача", "kind": "textarea", "required": True},
                {"name": "recommendations", "label": "Рекомендации", "kind": "textarea", "required": False},
            ]},
        ],
    }
    for visit in Visit.objects.all().iterator():
        if visit.completed_at or any(getattr(visit, name) for name in
                ("complaints", "anamnesis", "examination_result", "conclusion", "recommendations")):
            visit.form_type = "legacy"
            visit.form_version = 1
            visit.form_snapshot = snapshot
            visit.save(update_fields=["form_type", "form_version", "form_snapshot"])
        # Empty, unfinished documents bind to the service on first opening.


class Migration(migrations.Migration):
    dependencies = [("medical", "0003_medicalvisit_additional_data_and_more"),
                    ("billing", "0005_assign_medical_forms")]
    operations = [migrations.RunPython(preserve, migrations.RunPython.noop)]
