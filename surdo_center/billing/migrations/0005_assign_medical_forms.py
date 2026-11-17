from django.db import migrations


def assign(apps, schema_editor):
    Service = apps.get_model("billing", "Service")
    assignments = {
        "Первичный приём врача-сурдолога": "primary",
        "Повторный приём врача-сурдолога": "repeat",
        "Диагностика слуха": "hearing_diagnostic",
        "Консультация по результатам обследования": "results",
        "Краткая консультация": "brief",
        "Расширенный приём": "extended",
    }
    # One-time explicit assignment; runtime routing never depends on the name.
    for name, code in assignments.items():
        Service.objects.filter(service_name=name).update(medical_form_type=code, medical_form_version=1)


class Migration(migrations.Migration):
    dependencies = [("billing", "0004_service_medical_form_type_and_more")]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
