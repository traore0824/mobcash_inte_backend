"""
Sauvegarde les champs chiffrés AVANT migrate / AlterField dangereux.

Usage :
    python3 manage.py backup_encrypted_fields
    python3 manage.py backup_encrypted_fields --output /tmp/keys_backup.json
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from mobcash_inte.management.encrypted_fields_io import (
    backup_encrypted_fields,
    default_backup_path,
    write_backup,
)


class Command(BaseCommand):
    help = (
        "Backup brut des clés chiffrées (AppName hash/cashierpass, "
        "Setting connect_pro_token/refresh) avant migrations risquées."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default="",
            help="Chemin du fichier JSON (défaut: .encrypted_fields_backup.json)",
        )

    def handle(self, *args, **options):
        out = Path(options["output"]) if options["output"] else default_backup_path()
        payload = backup_encrypted_fields()
        write_backup(payload, out)

        apps = payload.get("app_names") or []
        settings_rows = payload.get("settings") or []
        apps_with_hash = sum(1 for a in apps if a.get("hash"))
        apps_with_pass = sum(1 for a in apps if a.get("cashierpass"))
        settings_with_token = sum(1 for s in settings_rows if s.get("connect_pro_token"))

        self.stdout.write(self.style.SUCCESS(f"Backup écrit → {out}"))
        self.stdout.write(f"  AppName     : {len(apps)} (hash={apps_with_hash}, cashierpass={apps_with_pass})")
        self.stdout.write(
            f"  Setting     : {len(settings_rows)} (connect_pro_token={settings_with_token})"
        )
        self.stdout.write(
            self.style.WARNING(
                "Ensuite : migrate, puis python3 manage.py restore_encrypted_fields"
            )
        )
