from django.core.management.base import BaseCommand

from predictions.services.pipeline import train_all_domestic_models


class Command(BaseCommand):
    help = "Entraîne Dixon-Coles (penaltyblog) sur football-data.co.uk pour les ligues domestiques"

    def handle(self, *args, **options):
        result = train_all_domestic_models()
        self.stdout.write(self.style.SUCCESS(str(result)))
