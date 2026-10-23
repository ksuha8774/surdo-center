from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Однократно переносит сохранённое состояние начальной версии в пустую PostgreSQL"

    def handle(self, *args, **options):
        if User.objects.exists():
            self.stdout.write("В PostgreSQL уже есть пользователи — перенос исходного состояния не требуется.")
            return

        fixture = Path(settings.BASE_DIR) / ".local-backups" / "sqlite_initial_export_2026-10-14.json"
        if not fixture.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Локальный экспорт начального состояния не найден. База останется пустой."
                )
            )
            return

        call_command("loaddata", str(fixture), verbosity=1)
        self.stdout.write(self.style.SUCCESS("Начальное состояние перенесено в PostgreSQL."))
