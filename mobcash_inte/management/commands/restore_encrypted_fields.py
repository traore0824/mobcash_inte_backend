"""
Restaure les champs chiffrés APRÈS migrate (valeurs brutes, sans re-encrypt).

Usage :
    python3 manage.py restore_encrypted_fields
    python3 manage.py restore_encrypted_fields --input /tmp/keys_backup.json
    python3 manage.py restore_encrypted_fields --dry-run
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from mobcash_inte.management.encrypted_fields_io import (
    default_backup_path,
    load_backup,
    restore_encrypted_fields,
)


class Command(BaseCommand):
    help = (
        "Restore brut des clés chiffrées depuis le JSON de backup_encrypted_fields "
        "(UPDATE SQL direct → aucun double chiffrement)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            "-i",
            type=str,
            default="",
            help="Chemin du JSON de backup (défaut: .encrypted_fields_backup.json)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simule sans écrire en DB",
        )

    def handle(self, *args, **options):
        path = Path(options["input"]) if options["input"] else default_backup_path()
        if not path.exists():
            raise CommandError(f"Fichier backup introuvable: {path}")

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY-RUN — aucune écriture ==="))

        payload = load_backup(path)
        stats = restore_encrypted_fields(payload, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS(f"Restore depuis → {path}"))
        self.stdout.write(
            f"  AppName  : restored={stats['apps_restored']} skipped={stats['apps_skipped']}"
        )
        self.stdout.write(
            f"  Setting  : restored={stats['settings_restored']} skipped={stats['settings_skipped']}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN terminé — DB inchangée."))
        else:
            self.stdout.write(self.style.SUCCESS("Restore terminé."))
