"""Championnats actifs et mapping API-Football / football-data.co.uk."""

# Codes CSV : https://www.football-data.co.uk/mmz4281/{season}/{code}.csv
LEAGUES = {
    "premier_league": {
        "provider_id": 39,
        "name": "Premier League",
        "country": "England",
        "football_data_code": "E0",
        "priority": 10,
    },
    "la_liga": {
        "provider_id": 140,
        "name": "La Liga",
        "country": "Spain",
        "football_data_code": "SP1",
        "priority": 20,
    },
    "ligue_1": {
        "provider_id": 61,
        "name": "Ligue 1",
        "country": "France",
        "football_data_code": "F1",
        "priority": 30,
    },
    "bundesliga": {
        "provider_id": 78,
        "name": "Bundesliga",
        "country": "Germany",
        "football_data_code": "D1",
        "priority": 40,
    },
    "serie_a": {
        "provider_id": 135,
        "name": "Serie A",
        "country": "Italy",
        "football_data_code": "I1",
        "priority": 50,
    },
    "champions_league": {
        "provider_id": 2,
        "name": "Champions League",
        "country": "World",
        "football_data_code": None,  # utilise un modèle agrégé des 5 grands
        "priority": 5,
    },
    "copa_del_rey": {
        "provider_id": 143,
        "name": "Coupe du Roi",
        "country": "Spain",
        "football_data_code": "SP1",  # forces La Liga comme proxy
        "priority": 60,
    },
}

PROVIDER_IDS = [cfg["provider_id"] for cfg in LEAGUES.values()]

# Saisons football-data (yy/yy+1 → dossier mmz4281)
FOOTBALL_DATA_SEASONS = ["2223", "2324", "2425"]

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
    "home_minus_15": "Domicile -1.5 buts",
    "home_minus_25": "Domicile -2.5 buts",
    "away_minus_15": "Extérieur -1.5 buts",
}

# Alias API-Football → noms football-data.co.uk
TEAM_ALIASES = {
    "paris saint germain": ["psg", "paris sg", "paris saint-germain", "paris"],
    "manchester united": ["man united", "man utd"],
    "manchester city": ["man city"],
    "newcastle united": ["newcastle"],
    "nottingham forest": ["Nott'm Forest", "nottingham"],
    "wolverhampton wanderers": ["wolves", "wolverhampton"],
    "tottenham hotspur": ["tottenham", "spurs"],
    "west ham united": ["west ham"],
    "brighton": ["brighton and hove albion", "brighton & hove albion"],
    "atletico madrid": ["atlético madrid", "atletico", "ath madrid"],
    "athletic club": ["athletic bilbao", "ath bilbao"],
    "real sociedad": ["sociedad"],
    "real betis": ["betis"],
    "bayern munich": ["bayern", "bayern münchen", "bayern munchen"],
    "borussia dortmund": ["dortmund"],
    "borussia monchengladbach": ["m'gladbach", "gladbach", "monchengladbach"],
    "eintracht frankfurt": ["frankfurt", "ein frankfurt"],
    "fc koln": ["1. fc köln", "1. fc koln", "fc cologne", "koln", "köln"],
    "rb leipzig": ["leipzig"],
    "bayer leverkusen": ["leverkusen"],
    "inter": ["inter milan", "internazionale"],
    "ac milan": ["milan"],
    "as roma": ["roma"],
    "ssc napoli": ["napoli"],
    "hellas verona": ["verona"],
    "deportivo la coruna": ["deportivo", "la coruna", "deportivo la coruña", "la coruña"],
    "1. fc koln": ["fc koln", "koln", "köln", "cologne", "fc cologne"],
    "levante": ["levante ud"],
}
