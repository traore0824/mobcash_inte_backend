"""Client API-Football (api-sports.io) — quota free 100 req/jour."""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
CACHE_TTL = 60 * 30  # 30 min


class ApiFootballError(Exception):
    pass


class ApiFootballClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY", "").strip()
        if not self.api_key:
            raise ApiFootballError(
                "API_FOOTBALL_KEY manquante. Ajoutez-la dans le .env "
                "(clé gratuite sur https://www.api-football.com/)."
            )

    def _get(self, path: str, params: dict | None = None, cache_key: str | None = None) -> Any:
        if cache_key:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        headers = {
            "x-apisports-key": self.api_key,
            "Accept": "application/json",
        }
        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
        except requests.RequestException as exc:
            raise ApiFootballError(f"Erreur réseau API-Football: {exc}") from exc

        if resp.status_code == 429:
            raise ApiFootballError("Quota API-Football dépassé (rate limit).")
        if resp.status_code >= 400:
            raise ApiFootballError(
                f"API-Football HTTP {resp.status_code}: {resp.text[:300]}"
            )

        payload = resp.json()
        errors = payload.get("errors")
        if errors:
            # API renvoie parfois errors: [] ou dict
            if isinstance(errors, dict) and errors:
                raise ApiFootballError(f"API-Football errors: {errors}")
            if isinstance(errors, list) and errors:
                raise ApiFootballError(f"API-Football errors: {errors}")

        remaining = resp.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            logger.info("API-Football quota restant: %s", remaining)

        data = payload.get("response", [])
        if cache_key:
            cache.set(cache_key, data, CACHE_TTL)
        return data

    def fixtures_by_date(self, day: date, league_ids: list[int] | None = None) -> list[dict]:
        """1 appel pour tous les matchs du jour, filtre local optionnel."""
        key = f"af:fixtures:{day.isoformat()}"
        data = self._get("/fixtures", params={"date": day.isoformat()}, cache_key=key)
        if not league_ids:
            return data
        allowed = set(league_ids)
        return [item for item in data if item.get("league", {}).get("id") in allowed]

    def fixtures_by_league_date(self, league_id: int, season: int, day: date) -> list[dict]:
        key = f"af:fixtures:{league_id}:{season}:{day.isoformat()}"
        return self._get(
            "/fixtures",
            params={"league": league_id, "season": season, "date": day.isoformat()},
            cache_key=key,
        )

    def current_season(self, league_id: int) -> int | None:
        key = f"af:season:{league_id}"
        data = self._get("/leagues", params={"id": league_id, "current": "true"}, cache_key=key)
        if not data:
            return None
        seasons = data[0].get("seasons") or []
        for season in seasons:
            if season.get("current"):
                return season.get("year")
        if seasons:
            return seasons[-1].get("year")
        return None
