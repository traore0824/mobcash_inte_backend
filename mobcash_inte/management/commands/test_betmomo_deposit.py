"""
Test direct d'un dépôt BetMomo via External API.

    python manage.py test_betmomo_deposit --token "dat_xxxxxxxx"
    python manage.py test_betmomo_deposit --token "dat_xxxxxxxx" --player-id 108464223 --amount 500
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from integrations.betmomo.client import BetmomoAPIError, BetmomoAuthError
from integrations.betmomo.service import BetMomoService
from integrations.betmomo.test_deposit import format_test_result, test_betmomo_deposit


class Command(BaseCommand):
    help = "Teste un dépôt BetMomo (topup) sur un player_id avec un token dat_..."

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            required=True,
            help="Token app dealer BeWallet (dat_...)",
        )
        parser.add_argument(
            "--player-id",
            default="108464223",
            help="ID joueur (défaut: 108464223)",
        )
        parser.add_argument(
            "--amount",
            type=float,
            default=100,
            help="Montant du dépôt (défaut: 100)",
        )
        parser.add_argument(
            "--base-url",
            default=None,
            help="URL de base BeWallet (sinon BEWALLET_EXTERNAL_API_BASE_URL)",
        )

    def handle(self, *args, **options):
        token = options["token"]
        player_id = options["player_id"]
        amount = options["amount"]
        base_url = options["base_url"]

        if base_url:
            request_url = f"{base_url.rstrip('/')}/dealer/external/topup"
        else:
            service = BetMomoService(token=token.strip())
            request_url = service.topup_request_url()

        self.stdout.write(
            self.style.WARNING(
                f"Test dépôt BetMomo — player_id={player_id}, amount={amount}"
            )
        )
        self.stdout.write(f"POST {request_url}")
        self.stdout.write(
            f"Base URL: {getattr(settings, 'BEWALLET_EXTERNAL_API_BASE_URL', '(non défini)')}"
        )

        try:
            result = test_betmomo_deposit(
                token=token,
                player_id=player_id,
                amount=amount,
                external_base_url=base_url,
            )
        except BetmomoAuthError as exc:
            raise CommandError(f"Auth échouée: {exc}\nURL appelée: POST {request_url}") from exc
        except BetmomoAPIError as exc:
            raise CommandError(f"API erreur: {exc}\nURL appelée: POST {request_url}") from exc
        except Exception as exc:
            raise CommandError(f"Erreur: {exc}\nURL appelée: POST {request_url}") from exc

        self.stdout.write(format_test_result(result))

        if result["failed"]:
            raise CommandError(f"Dépôt échoué — statut: {result['status']}")

        if result["pending"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dépôt en attente — reference: {result['operation_id']}"
                )
            )
        elif result["success"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dépôt réussi — reference: {result['operation_id']}"
                )
            )
