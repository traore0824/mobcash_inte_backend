"""Moteur de pronostics — Dixon-Coles (penaltyblog) + fallback heuristique."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from predictions.constants import MARKET_LABELS

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(getattr(settings, "BASE_DIR", Path("."))) / "predictions" / "artifacts"


@dataclass
class MarketPick:
    market: str
    label: str
    probability: float
    markets: dict[str, float]
    p_home: float
    p_draw: float
    p_away: float
    confidence: str
    model_name: str


def _confidence(prob: float) -> str:
    if prob >= 0.68:
        return "high"
    if prob >= 0.55:
        return "medium"
    return "low"


def _pick_best_market(markets: dict[str, float]) -> tuple[str, float]:
    """Choisit un marché actionnable (évite 12 quasi toujours vrai)."""
    # 12 = domicile ou extérieur ≈ 75 % en permanence → pas un « meilleur pari »
    excluded = {"double_chance_12"}
    preferred_order = [
        "over_25",
        "under_25",
        "double_chance_1x",
        "double_chance_x2",
        "ah_home_plus_1",
        "ah_away_plus_1",
        "home",
        "away",
        "draw",
    ]
    candidates = [
        (k, v)
        for k, v in markets.items()
        if k not in excluded and 0.54 <= v <= 0.82
    ]
    if not candidates:
        candidates = [
            (k, v) for k, v in markets.items() if k not in excluded and k in preferred_order
        ]
    if not candidates:
        candidates = [(k, v) for k, v in markets.items() if k not in excluded]

    def score(item: tuple[str, float]) -> tuple:
        key, prob = item
        # Favorise les marchés « tip » tout en gardant une proba élevée
        try:
            pref = len(preferred_order) - preferred_order.index(key)
        except ValueError:
            pref = 0
        return (prob, pref)

    return max(candidates, key=score)


def markets_from_grid(grid: Any) -> dict[str, float]:
    """Extrait les marchés depuis FootballProbabilityGrid (penaltyblog)."""
    home, draw, away = [float(x) for x in grid.home_draw_away]
    total = home + draw + away or 1.0
    home, draw, away = home / total, draw / total, away / total

    out = {
        "home": home,
        "draw": draw,
        "away": away,
        "double_chance_1x": home + draw,
        "double_chance_12": home + away,
        "double_chance_x2": draw + away,
    }

    # Over/Under 2.5
    try:
        out["over_25"] = float(grid.total_goals("over", 2.5))
        out["under_25"] = float(grid.total_goals("under", 2.5))
    except Exception:
        # Calcul manuel sur la matrice si API différente
        try:
            matrix = grid.grid
            over = 0.0
            under = 0.0
            for i, row in enumerate(matrix):
                for j, p in enumerate(row):
                    if i + j > 2:
                        over += float(p)
                    else:
                        under += float(p)
            s = over + under or 1.0
            out["over_25"] = over / s
            out["under_25"] = under / s
        except Exception:
            out["over_25"] = 0.5
            out["under_25"] = 0.5

    # Handicap asiatique approx +1 domicile / +1 extérieur
    try:
        out["ah_home_plus_1"] = float(home + draw)  # proche double chance 1X
        out["ah_away_plus_1"] = float(away + draw)
    except Exception:
        out["ah_home_plus_1"] = home + draw
        out["ah_away_plus_1"] = away + draw

    return out


def heuristic_markets(home_strength: float = 0.45, away_strength: float = 0.30) -> dict[str, float]:
    """Fallback sans modèle entraîné — avantage domicile léger."""
    draw = max(0.18, 1.0 - home_strength - away_strength)
    total = home_strength + draw + away_strength
    home = home_strength / total
    draw = draw / total
    away = away_strength / total
    return {
        "home": home,
        "draw": draw,
        "away": away,
        "double_chance_1x": home + draw,
        "double_chance_12": home + away,
        "double_chance_x2": draw + away,
        "over_25": 0.52,
        "under_25": 0.48,
        "ah_home_plus_1": home + draw,
        "ah_away_plus_1": away + draw,
    }


def build_pick_from_markets(markets: dict[str, float], model_name: str) -> MarketPick:
    market, prob = _pick_best_market(markets)
    return MarketPick(
        market=market,
        label=MARKET_LABELS.get(market, market),
        probability=round(prob, 4),
        markets={k: round(v, 4) for k, v in markets.items()},
        p_home=round(markets["home"], 4),
        p_draw=round(markets["draw"], 4),
        p_away=round(markets["away"], 4),
        confidence=_confidence(prob),
        model_name=model_name,
    )


class PredictionEngine:
    """Charge / entraîne Dixon-Coles par championnat domestique."""

    def __init__(self):
        self._models: dict[str, Any] = {}
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    def train_league(self, football_data_name: str, seasons: list[str] | None = None) -> str | None:
        """Entraîne un modèle Dixon-Coles via football-data.co.uk (gratuit)."""
        try:
            import pandas as pd
            import penaltyblog as pb
        except ImportError as exc:
            logger.warning("penaltyblog non installé: %s", exc)
            return None

        seasons = seasons or ["2022-2023", "2023-2024", "2024-2025"]
        frames = []
        for season in seasons:
            try:
                df = pb.scrapers.FootballData(football_data_name, season).get_fixtures()
                if df is not None and len(df):
                    frames.append(df)
            except Exception as exc:
                logger.info("Skip %s %s: %s", football_data_name, season, exc)

        if not frames:
            logger.warning("Pas d'historique pour %s", football_data_name)
            return None

        df = pd.concat(frames, ignore_index=True)
        # Colonnes attendues selon versions penaltyblog
        col_map = {
            "goals_home": ["goals_home", "fthg", "FTHG", "score_home"],
            "goals_away": ["goals_away", "ftag", "FTAG", "score_away"],
            "team_home": ["team_home", "home_team", "HomeTeam", "home"],
            "team_away": ["team_away", "away_team", "AwayTeam", "away"],
            "date": ["date", "Date"],
        }

        def resolve(cols):
            for c in cols:
                if c in df.columns:
                    return c
            return None

        gh_c = resolve(col_map["goals_home"])
        ga_c = resolve(col_map["goals_away"])
        th_c = resolve(col_map["team_home"])
        ta_c = resolve(col_map["team_away"])
        date_c = resolve(col_map["date"])

        if not all([gh_c, ga_c, th_c, ta_c]):
            logger.warning("Colonnes manquantes pour %s: %s", football_data_name, list(df.columns))
            return None

        df = df.dropna(subset=[gh_c, ga_c, th_c, ta_c])
        weights = None
        if date_c:
            try:
                weights = pb.models.dixon_coles_weights(df[date_c], xi=0.0018)
            except Exception:
                weights = None

        model_cls = getattr(pb.models, "DixonColesGoalsModel", None) or getattr(
            pb.models, "DixonColesGoalModel", None
        )
        if model_cls is None:
            logger.error("DixonColes model class introuvable dans penaltyblog")
            return None

        kwargs = {}
        if weights is not None:
            kwargs["weights"] = weights
        model = model_cls(df[gh_c], df[ga_c], df[th_c], df[ta_c], **kwargs)
        model.fit()

        safe_name = football_data_name.replace(" ", "_").lower()
        path = ARTIFACT_DIR / f"{safe_name}.pkl"
        try:
            model.save(str(path))
        except Exception:
            import pickle

            with open(path, "wb") as f:
                pickle.dump(model, f)

        self._models[football_data_name] = model
        logger.info("Modèle entraîné: %s → %s", football_data_name, path)
        return str(path)

    def load_league(self, football_data_name: str) -> Any | None:
        if football_data_name in self._models:
            return self._models[football_data_name]

        safe_name = football_data_name.replace(" ", "_").lower()
        path = ARTIFACT_DIR / f"{safe_name}.pkl"
        if not path.exists():
            return None

        try:
            import penaltyblog as pb

            model_cls = getattr(pb.models, "DixonColesGoalsModel", None) or getattr(
                pb.models, "DixonColesGoalModel", None
            )
            if model_cls and hasattr(model_cls, "load"):
                model = model_cls.load(str(path))
            else:
                import pickle

                with open(path, "rb") as f:
                    model = pickle.load(f)
            self._models[football_data_name] = model
            return model
        except Exception as exc:
            logger.warning("Impossible de charger %s: %s", path, exc)
            return None

    def predict_match(
        self,
        home_name: str,
        away_name: str,
        football_data_name: str | None,
    ) -> MarketPick:
        model = None
        if football_data_name:
            model = self.load_league(football_data_name)
            if model is None:
                try:
                    self.train_league(football_data_name)
                    model = self.load_league(football_data_name)
                except Exception as exc:
                    logger.warning("Train failed %s: %s", football_data_name, exc)

        if model is not None:
            try:
                # Normaliser noms d'équipes courants
                home = self._resolve_team(model, home_name)
                away = self._resolve_team(model, away_name)
                if home and away:
                    grid = model.predict(home, away)
                    markets = markets_from_grid(grid)
                    return build_pick_from_markets(markets, model_name="dixon_coles_v1")
            except Exception as exc:
                logger.info("Predict fallback (%s vs %s): %s", home_name, away_name, exc)

        markets = heuristic_markets()
        return build_pick_from_markets(markets, model_name="heuristic_v1")

    def _resolve_team(self, model: Any, name: str) -> str | None:
        candidates = set()
        for attr in ("teams", "team_names", "attackers", "params"):
            val = getattr(model, attr, None)
            if isinstance(val, dict):
                candidates.update(str(k) for k in val.keys())
            elif isinstance(val, (list, set, tuple)):
                candidates.update(str(x) for x in val)

        if name in candidates:
            return name

        # Match flou simple
        norm = name.lower().replace(".", "").strip()
        aliases = {
            "paris saint germain": ["psg", "paris sg", "paris saint-germain"],
            "manchester united": ["man united", "man utd"],
            "manchester city": ["man city"],
            "atletico madrid": ["atlético madrid", "atletico de madrid"],
            "inter": ["inter milan", "fc internazionale"],
            "bayern munich": ["bayern münchen", "fc bayern"],
        }
        for team in candidates:
            t = team.lower().replace(".", "").strip()
            if t == norm or norm in t or t in norm:
                return team
            for canon, al in aliases.items():
                if norm == canon or norm in al:
                    if t == canon or t in al or canon in t:
                        return team
        return None


def settle_market(market: str, score_home: int, score_away: int) -> bool | None:
    """True = gagné, False = perdu, None = non déterminable."""
    total = score_home + score_away
    diff = score_home - score_away

    if market == "home":
        return score_home > score_away
    if market == "draw":
        return score_home == score_away
    if market == "away":
        return score_home < score_away
    if market == "double_chance_1x":
        return score_home >= score_away
    if market == "double_chance_12":
        return score_home != score_away
    if market == "double_chance_x2":
        return score_home <= score_away
    if market == "over_25":
        return total > 2
    if market == "under_25":
        return total < 3
    if market == "ah_home_plus_1":
        return (score_home + 1) > score_away
    if market == "ah_away_plus_1":
        return (score_away + 1) > score_home
    return None
