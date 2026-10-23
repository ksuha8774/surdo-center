from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="medicalvisit",
            constraint=models.CheckConstraint(
                condition=models.Q(("completed_at__isnull", True), ("completed_at__gte", models.F("started_at")), _connector="OR"),
                name="medical_visit_completion_order",
            ),
        ),
    ]
