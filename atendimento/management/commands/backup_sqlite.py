from datetime import datetime
from pathlib import Path
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Cria uma cópia consistente do banco SQLite na pasta backups."

    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        if not source.exists():
            raise CommandError(f"Banco ainda não existe: {source}")
        backup_dir = settings.BASE_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"banco_{stamp}.sqlite3"
        try:
            with sqlite3.connect(source) as db, sqlite3.connect(target) as backup:
                db.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise CommandError(f"Verificação do backup falhou: {result}")
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise CommandError(f"Não foi possível criar o backup: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Backup verificado: {target}"))
