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
- `GET /mobcash/predictions/` (staff) — consultation admin, sans verrou dépôt/retrait :
  `?date=YYYY-MM-DD&outcome=won|lost|pending|void&search=...&page=1&page_size=20`
  (retourne aussi un `summary` : total, gagnés, perdus, en attente, taux de réussite)

## Admin web

La page « Pronostics » du dashboard (`mobcash-master-admin`) est masquée par défaut.
Pour l'activer, ajouter dans le `.env` du dashboard :

```
NEXT_PUBLIC_ENABLE_PREDICTIONS="true"
```

Puis relancer le build / redémarrer le front. Le flag ne concerne que l'affichage
admin : le pipeline Celery et l'API mobile continuent de fonctionner normalement.

## Championnats

Premier League, La Liga, Ligue 1, Bundesliga, Serie A, Champions League, Coupe du Roi.
