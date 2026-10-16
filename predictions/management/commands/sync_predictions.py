from django.core.management.base import BaseCommand

from predictions.services.pipeline import run_daily_pipeline, run_update_pipeline


class Command(BaseCommand):
    help = "Sync matchs du jour + génère / met à jour les pronos (API-Football + moteur)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["daily", "update"],
            default="daily",
            help="daily = création du jour ; update = refresh 3h",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        if mode == "update":
            result = run_update_pipeline()
        else:
            result = run_daily_pipeline()
        self.stdout.write(self.style.SUCCESS(str(result)))
