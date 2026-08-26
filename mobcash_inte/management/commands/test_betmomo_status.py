"""
Vérifie le statut d'une opération BetMomo (topup ou payout).

    python manage.py test_betmomo_status --token "dat_..." --reference BWTSP...
    python manage.py test_betmomo_status --token "dat_..." --reference TXN-... --type payout
"""

from django.core.management.base import BaseCommand, CommandError

from integrations.betmomo.client import BetmomoAPIError, BetmomoAuthError
from integrations.betmomo.test_status import format_status_result, test_betmomo_status


class Command(BaseCommand):
    help = "Vérifie le statut d'un topup ou payout BetMomo via External API"

    def add_arguments(self, parser):
        parser.add_argument("--token", required=True, help="Token app dealer (dat_...)")
        parser.add_argument(
            "--reference",
            required=True,
            help="Référence topup (ex: BWTSP...) ou transaction_id payout",
        )
        parser.add_argument(
            "--type",
            dest="op_type",
            default="topup",
            choices=["topup", "payout", "deposit", "withdrawal"],
            help="Type d'opération (défaut: topup)",
        )

    def handle(self, *args, **options):
        token = options["token"]
        reference = options["reference"]
        op_type = options["op_type"]

        self.stdout.write(
            self.style.WARNING(
                f"Vérification statut BetMomo — type={op_type}, reference={reference}"
            )
        )

        try:
            result = test_betmomo_status(
                token=token,
                reference=reference,
                op_type=op_type,
            )
        except BetmomoAuthError as exc:
            raise CommandError(f"Auth échouée: {exc}") from exc
        except BetmomoAPIError as exc:
            raise CommandError(f"API erreur: {exc}") from exc
        except Exception as exc:
            raise CommandError(f"Erreur: {exc}") from exc

        self.stdout.write(format_status_result(result))

        if not result["found"]:
            raise CommandError("Opération introuvable ou erreur API")

        status = result["status"]
        if status == "success":
            self.stdout.write(self.style.SUCCESS(f"Statut confirmé: {status}"))
        elif status == "failed":
            self.stdout.write(self.style.ERROR(f"Statut: {status}"))
        else:
            self.stdout.write(self.style.WARNING(f"Statut: {status or 'pending'}"))
