from django.core.management.base import BaseCommand, CommandError

from connect_withdrawal_test import connect_withdrawal_test


class Command(BaseCommand):
    help = (
        "Teste un retrait Connect Pro (appel API uniquement, aucune transaction en base). "
        "Usage: python3 manage.py connect_withdrawal_test <network> <phone> <amount>"
    )

    def add_arguments(self, parser):
        parser.add_argument("network", type=str, help="Réseau: moov, mtn, wave ou MOOV-BJ")
        parser.add_argument("phone", type=str, help="Numéro bénéficiaire (ex: 2290155187395)")
        parser.add_argument("amount", type=int, help="Montant en FCFA")

    def handle(self, *args, **options):
        network = options["network"].strip()
        phone = options["phone"].strip().replace(" ", "")
        amount = options["amount"]

        if amount <= 0:
            raise CommandError("Le montant doit être supérieur à 0.")

        self.stdout.write(
            self.style.NOTICE(
                f"=== Test connect_withdrawal | réseau={network} | phone={phone} | amount={amount} ==="
            )
        )

        result = connect_withdrawal_test(
            network_name=network,
            phone_number=phone,
            amount=amount,
        )

        if result is None:
            raise CommandError("Échec du test connect_withdrawal.")

        self.stdout.write(self.style.SUCCESS("=== Test terminé ==="))
