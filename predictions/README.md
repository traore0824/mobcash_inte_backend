# Module Predictions (TurainCash Pronos)

## Setup

1. Ajouter dans `.env` :
   ```
   API_FOOTBALL_KEY=votre_cle_gratuite
   ```
   Clé : https://dashboard.api-football.com/

2. Installer les deps :
   ```bash
   pip install -r requirements.txt
   ```

3. Migrer :
   ```bash
   python manage.py migrate predictions
   ```

4. (Optionnel) Entraîner Dixon-Coles sur les ligues domestiques :
   ```bash
   python manage.py train_prediction_models
   ```

5. Sync du jour :
   ```bash
   python manage.py sync_predictions --mode daily
   ```

## Celery

Queue dédiée `predictions` :

```bash
celery -A mobcash_inte_backend worker -Q predictions -l info
celery -A mobcash_inte_backend beat -l info
```

- `01:00` UTC : création des pronos du jour
- toutes les `3 h` : update scores + Gagné/Perdu

## API

- `GET /api/v1/predictions/today/` (JWT) — cartes du **jour uniquement**, groupées par championnat
- `GET /api/v1/predictions/settings/`

## Championnats

Premier League, La Liga, Ligue 1, Bundesliga, Serie A, Champions League, Coupe du Roi.
