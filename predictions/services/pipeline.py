"""Orchestration sync fixtures + génération / settlement des prédictions."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from predictions.constants import LEAGUES, PROVIDER_IDS
from predictions.models import Competition, Fixture, ModelVersion, Prediction, Team
from predictions.services.api_football import ApiFootballClient, ApiFootballError
from predictions.services.engine import PredictionEngine, settle_market

logger = logging.getLogger(__name__)


def _map_status(short: str | None, long: str | None = None) -> str:
    s = (short or "").upper()
    if s in {"NS", "TBD", "SCH"}:
        return Fixture.Status.SCHEDULED
    if s in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INT"}:
        return Fixture.Status.LIVE
    if s in {"FT", "AET", "PEN"}:
        return Fixture.Status.FINISHED
    if s in {"PST", "SUSP"}:
        return Fixture.Status.POSTPONED
    if s in {"CANC", "ABD", "AWD", "WO"}:
        return Fixture.Status.CANCELLED
    if long and "progress" in long.lower():
        return Fixture.Status.LIVE
    return Fixture.Status.SCHEDULED


def ensure_competitions() -> dict[int, Competition]:
    mapping = {}
    for slug, cfg in LEAGUES.items():
        obj, _ = Competition.objects.update_or_create(
            provider_id=cfg["provider_id"],
            defaults={
                "slug": slug,
                "name": cfg["name"],
                "country": cfg["country"],
                "priority": cfg["priority"],
                "is_active": True,
            },
        )
        mapping[cfg["provider_id"]] = obj
    return mapping


def _upsert_team(raw: dict) -> Team:
    team, _ = Team.objects.update_or_create(
        provider_id=raw["id"],
        defaults={
            "name": raw.get("name") or f"Team {raw['id']}",
            "logo": raw.get("logo") or "",
            "country": "",
        },
    )
    return team


def _parse_kickoff(raw: dict):
    date_block = raw.get("fixture", {}).get("date")
    if not date_block:
        return timezone.now()
    dt = parse_datetime(date_block)
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


@transaction.atomic
def upsert_fixture_payload(item: dict, competitions: dict[int, Competition]) -> Fixture | None:
    league = item.get("league") or {}
    league_id = league.get("id")
    if league_id not in competitions:
        return None

    fixture_raw = item.get("fixture") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    status_block = fixture_raw.get("status") or {}

    home = _upsert_team(teams.get("home") or {})
    away = _upsert_team(teams.get("away") or {})
    if not home.provider_id or not away.provider_id:
        return None

    competition = competitions[league_id]
    season = league.get("season")
    if season and competition.season != season:
        competition.season = season
        if league.get("logo"):
            competition.logo = league["logo"]
        competition.save(update_fields=["season", "logo"])

    status = _map_status(status_block.get("short"), status_block.get("long"))
    fixture, _ = Fixture.objects.update_or_create(
        provider_id=fixture_raw["id"],
        defaults={
            "competition": competition,
            "home": home,
            "away": away,
            "kickoff_at": _parse_kickoff(item),
            "status": status,
            "minute": status_block.get("elapsed"),
            "score_home": goals.get("home"),
            "score_away": goals.get("away"),
            "round_name": league.get("round") or "",
            "last_synced_at": timezone.now(),
        },
    )
    return fixture


def sync_fixtures_for_day(day: date | None = None) -> dict:
    """1 appel API-Football pour la date, filtre nos 7 championnats."""
    day = day or timezone.localdate()
    competitions = ensure_competitions()
    client = ApiFootballClient()
    raw = client.fixtures_by_date(day, league_ids=PROVIDER_IDS)
    created = 0
    for item in raw:
        fx = upsert_fixture_payload(item, competitions)
        if fx:
            created += 1
    return {"date": day.isoformat(), "fixtures": created, "api_items": len(raw)}


def ensure_active_model(name: str = "dixon_coles_v1") -> ModelVersion:
    mv = ModelVersion.objects.filter(name=name, is_active=True).first()
    if mv:
        return mv
    return ModelVersion.objects.create(name=name, is_active=True, params={})


def generate_predictions_for_day(day: date | None = None) -> dict:
    """Crée / met à jour les prédictions du jour (non figées)."""
    day = day or timezone.localdate()
    engine = PredictionEngine()
    model_version = ensure_active_model()
    slug_to_fd = {
        slug: cfg.get("football_data_name") for slug, cfg in LEAGUES.items()
    }

    fixtures = (
        Fixture.objects.filter(
            kickoff_at__date=day,
            status__in=[Fixture.Status.SCHEDULED, Fixture.Status.LIVE, Fixture.Status.FINISHED],
            competition__is_active=True,
        )
        .select_related("home", "away", "competition")
    )

    created = 0
    updated = 0
    for fixture in fixtures:
        existing = Prediction.objects.filter(fixture=fixture).first()
        if existing and existing.is_locked:
            continue

        fd_name = slug_to_fd.get(fixture.competition.slug)
        pick = engine.predict_match(fixture.home.name, fixture.away.name, fd_name)

        defaults = {
            "model_version": model_version,
            "p_home": pick.p_home,
            "p_draw": pick.p_draw,
            "p_away": pick.p_away,
            "best_market": pick.market,
            "best_market_label": pick.label,
            "best_market_prob": pick.probability,
            "confidence_level": pick.confidence,
            "markets": pick.markets,
            "prediction_date": day,
            "is_published": True,
            "published_at": timezone.now(),
        }

        # Verrouiller au coup d'envoi / live / finished
        if fixture.status in {Fixture.Status.LIVE, Fixture.Status.FINISHED}:
            defaults["locked_at"] = fixture.kickoff_at

        pred, was_created = Prediction.objects.update_or_create(
            fixture=fixture, defaults=defaults
        )
        if was_created:
            created += 1
        else:
            updated += 1

        # Settlement immédiat si FT
        if fixture.status == Fixture.Status.FINISHED:
            settle_prediction(pred)

    return {"date": day.isoformat(), "created": created, "updated": updated}


def settle_prediction(prediction: Prediction) -> None:
    fixture = prediction.fixture
    if fixture.score_home is None or fixture.score_away is None:
        return
    if prediction.outcome != Prediction.Outcome.PENDING and prediction.settled_at:
        return

    result = settle_market(
        prediction.best_market, fixture.score_home, fixture.score_away
    )
    if result is None:
        prediction.outcome = Prediction.Outcome.VOID
    elif result:
        prediction.outcome = Prediction.Outcome.WON
    else:
        prediction.outcome = Prediction.Outcome.LOST
    prediction.settled_at = timezone.now()
    if not prediction.locked_at:
        prediction.locked_at = fixture.kickoff_at
    prediction.save(update_fields=["outcome", "settled_at", "locked_at"])


def settle_finished_for_day(day: date | None = None) -> int:
    day = day or timezone.localdate()
    qs = Prediction.objects.filter(
        prediction_date=day,
        outcome=Prediction.Outcome.PENDING,
        fixture__status=Fixture.Status.FINISHED,
    ).select_related("fixture")
    count = 0
    for pred in qs:
        settle_prediction(pred)
        count += 1
    return count


def run_daily_pipeline() -> dict:
    """01:00 — sync jour + génération des cartes."""
    today = timezone.localdate()
    sync = sync_fixtures_for_day(today)
    preds = generate_predictions_for_day(today)
    settled = settle_finished_for_day(today)
    return {"sync": sync, "predictions": preds, "settled": settled}


def run_update_pipeline() -> dict:
    """Toutes les 2–3 h — refresh scores + settlement + nouveaux matchs du jour."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    sync_today = sync_fixtures_for_day(today)
    # 1 appel pour hier (settlement des matchs finissant après minuit)
    try:
        sync_yesterday = sync_fixtures_for_day(yesterday)
    except ApiFootballError as exc:
        logger.warning("Sync hier échoué: %s", exc)
        sync_yesterday = {"error": str(exc)}

    preds = generate_predictions_for_day(today)
    settled_today = settle_finished_for_day(today)
    settled_yesterday = settle_finished_for_day(yesterday)
    return {
        "sync_today": sync_today,
        "sync_yesterday": sync_yesterday,
        "predictions": preds,
        "settled_today": settled_today,
        "settled_yesterday": settled_yesterday,
    }


def train_all_domestic_models() -> dict:
    engine = PredictionEngine()
    results = {}
    for slug, cfg in LEAGUES.items():
        name = cfg.get("football_data_name")
        if not name:
            continue
        path = engine.train_league(name)
        results[slug] = path
        if path:
            ModelVersion.objects.create(
                name="dixon_coles_v1",
                is_active=True,
                artifact_path=path,
                params={"league": slug, "source": name},
            )
    # Désactiver les anciennes versions sauf la dernière par ligue
    return results
