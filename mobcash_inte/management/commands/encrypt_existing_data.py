"""
Management command : encrypt_existing_data
==========================================
À lancer UNE SEULE FOIS après le premier déploiement pour chiffrer
les valeurs en clair déjà présentes en DB.

Usage :
    python manage.py encrypt_existing_data
    python manage.py encrypt_existing_data --dry-run   # simulation sans écriture

Champs concernés :
    - AppName   : hash, cashierpass
    - Setting   : connect_pro_token, connect_pro_refresh
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from cryptography.fernet import InvalidToken

from crypto_fields import encrypt, decrypt


def _is_already_encrypted(value: str | None) -> bool:
    """
    Tente de déchiffrer. Si ça réussit sans lever InvalidToken,
    la valeur est déjà un token Fernet valide.
    Fernet tokens commencent toujours par 'gAAAAA'.
    """
    if not value:
        return True  # rien à faire
    return value.startswith("gAAAAA")


class Command(BaseCommand):
    help = "Chiffre les valeurs en clair existantes en DB (AppName.hash/cashierpass, Setting.connect_pro_token/refresh)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simule sans écrire en DB",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== MODE DRY-RUN — aucune écriture ===\n"))

        total_encrypted = 0
        total_skipped = 0
        total_empty = 0

        # ── AppName ────────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("▶ AppName (hash, cashierpass)"))

        from accounts.models import AppName

        app_names = AppName.objects.all()
        self.stdout.write(f"  {app_names.count()} enregistrements trouvés")

        for app in app_names:
            changed = False

            # hash
            raw_hash = app._hash
            if not raw_hash:
                total_empty += 1
            elif _is_already_encrypted(raw_hash):
                self.stdout.write(f"  [{app.name}] hash → déjà chiffré, skip")
                total_skipped += 1
            else:
                self.stdout.write(f"  [{app.name}] hash → chiffrement en clair '{raw_hash[:6]}...'")
                if not dry_run:
                    app._hash = encrypt(raw_hash)
                changed = True
                total_encrypted += 1

            # cashierpass
            raw_pass = app._cashierpass
            if not raw_pass:
                total_empty += 1
            elif _is_already_encrypted(raw_pass):
                self.stdout.write(f"  [{app.name}] cashierpass → déjà chiffré, skip")
                total_skipped += 1
            else:
                self.stdout.write(f"  [{app.name}] cashierpass → chiffrement en clair")
                if not dry_run:
                    app._cashierpass = encrypt(raw_pass)
                changed = True
                total_encrypted += 1

            if changed and not dry_run:
                app.save(update_fields=["_hash", "_cashierpass"])

        # ── Setting ────────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Setting (connect_pro_token, connect_pro_refresh)"))

        from mobcash_inte.models import Setting

        settings_qs = Setting.objects.all()
        self.stdout.write(f"  {settings_qs.count()} enregistrements trouvés")

        for setting in settings_qs:
            changed = False

            # connect_pro_token
            raw_token = setting._connect_pro_token
            if not raw_token:
                total_empty += 1
            elif _is_already_encrypted(raw_token):
                self.stdout.write(f"  [Setting #{setting.id}] connect_pro_token → déjà chiffré, skip")
                total_skipped += 1
            else:
                self.stdout.write(f"  [Setting #{setting.id}] connect_pro_token → chiffrement en clair")
                if not dry_run:
                    setting._connect_pro_token = encrypt(raw_token)
                changed = True
                total_encrypted += 1

            # connect_pro_refresh
            raw_refresh = setting._connect_pro_refresh
            if not raw_refresh:
                total_empty += 1
            elif _is_already_encrypted(raw_refresh):
                self.stdout.write(f"  [Setting #{setting.id}] connect_pro_refresh → déjà chiffré, skip")
                total_skipped += 1
            else:
                self.stdout.write(f"  [Setting #{setting.id}] connect_pro_refresh → chiffrement en clair")
                if not dry_run:
                    setting._connect_pro_refresh = encrypt(raw_refresh)
                changed = True
                total_encrypted += 1

            if changed and not dry_run:
                setting.save(update_fields=["_connect_pro_token", "_connect_pro_refresh"])

        # ── Résumé ─────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"✅ Chiffrés    : {total_encrypted}"))
        self.stdout.write(self.style.WARNING(f"⏭  Déjà OK     : {total_skipped}"))
        self.stdout.write(f"○  Vides/null  : {total_empty}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY-RUN : rien n'a été écrit en DB."))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ Migration terminée."))
