"""Corrige les pronostics « handicap +1 » comptés Perdu alors qu'ils étaient remboursés."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from predictions.models import Prediction
from predictions.services.engine import settle_market

PUSH_MARKETS = {"ah_home_plus_1", "ah_away_plus_1"}


class Command(BaseCommand):
    help = (
        "Repasse en Annulé (void) les pronostics handicap +1 marqués Perdu "
        "alors que le match s'est terminé sur un push."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les corrections sans les appliquer.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        qs = (
            Prediction.objects.filter(
                outcome=Prediction.Outcome.LOST,
                best_market__in=PUSH_MARKETS,
            )
            .select_related("fixture")
        )

        fixed = 0
        for prediction in qs:
            fixture = prediction.fixture
            if fixture.score_home is None or fixture.score_away is None:
                continue
            result = settle_market(
                prediction.best_market, fixture.score_home, fixture.score_away
            )
            if result is not None:
                continue

            self.stdout.write(
                f"#{prediction.id} {prediction.best_market} "
                f"{fixture.score_home}-{fixture.score_away} "
                f"{prediction.prediction_date} : perdu -> annulé"
            )
            if not dry_run:
                prediction.outcome = Prediction.Outcome.VOID
                prediction.settled_at = timezone.now()
                prediction.save(update_fields=["outcome", "settled_at"])
            fixed += 1

        label = "à corriger" if dry_run else "corrigés"
        self.stdout.write(self.style.SUCCESS(f"{fixed} pronostic(s) {label}."))
