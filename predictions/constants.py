"""Championnats actifs et mapping API-Football."""

# API-Football league IDs (v3)
LEAGUES = {
    "premier_league": {
        "provider_id": 39,
        "name": "Premier League",
        "country": "England",
        "football_data_name": "ENG Premier League",
        "priority": 10,
    },
    "la_liga": {
        "provider_id": 140,
        "name": "La Liga",
        "country": "Spain",
        "football_data_name": "ESP La Liga",
        "priority": 20,
    },
    "ligue_1": {
        "provider_id": 61,
        "name": "Ligue 1",
        "country": "France",
        "football_data_name": "FRA Ligue 1",
        "priority": 30,
    },
    "bundesliga": {
        "provider_id": 78,
        "name": "Bundesliga",
        "country": "Germany",
        "football_data_name": "DEU Bundesliga",
        "priority": 40,
    },
    "serie_a": {
        "provider_id": 135,
        "name": "Serie A",
        "country": "Italy",
        "football_data_name": "ITA Serie A",
        "priority": 50,
    },
    "champions_league": {
        "provider_id": 2,
        "name": "Champions League",
        "country": "World",
        "football_data_name": None,
        "priority": 5,
    },
    "copa_del_rey": {
        "provider_id": 143,
        "name": "Coupe du Roi",
        "country": "Spain",
        "football_data_name": None,
        "priority": 60,
    },
}

PROVIDER_IDS = [cfg["provider_id"] for cfg in LEAGUES.values()]

# Markets exposés comme « Meilleur pari »
MARKET_LABELS = {
    "home": "Victoire domicile",
    "draw": "Match nul",
    "away": "Victoire extérieur",
    "double_chance_1x": "Double chance 1X",
    "double_chance_12": "Double chance 12",
    "double_chance_x2": "Double chance X2",
    "over_25": "Plus de 2.5 buts",
    "under_25": "Moins de 2.5 buts",
    "ah_home_plus_1": "Handicap dom +1",
    "ah_away_plus_1": "Handicap ext +1",
}
