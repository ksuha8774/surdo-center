from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ExternalSystem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True, verbose_name="Код")),
                ("name", models.CharField(max_length=120, verbose_name="Название")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
            ],
        ),
    ]
