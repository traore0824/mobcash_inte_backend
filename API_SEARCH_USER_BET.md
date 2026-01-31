# Documentation API - Recherche d'Utilisateur (SearchUserBet)

## Endpoint

```
POST /mobcash/search-user
```

## Description

Recherche un utilisateur/joueur sur une plateforme de paris (app) par son ID utilisateur.

## Body (JSON)

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `userid` | string | Oui | ID de l'utilisateur à rechercher |
| `app_id` | string | Non | ID de l'application (UUID) |
| `app_name` | string | Non | Nom de l'application |

**Note :** Vous devez fournir soit `app_id` soit `app_name` (au moins un des deux est requis).

### Exemple de Body

```json
{
  "userid": "339966934",
  "app_name": "1xbet"
}
```

ou

```json
{
  "userid": "339966934",
  "app_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Response

### Success (200 OK)

Le format de la réponse dépend de l'application :

#### Si l'app a un hash (app avec hash)

Retourne les données de l'utilisateur depuis l'API externe :

```json
{
  "UserId": 123456,
  "Name": "Nom du joueur",
  "CurrencyId": 1,
  // ... autres champs selon l'API externe
}
```

Si une erreur survient lors de l'appel externe, retourne un objet vide :

```json
{}
```

#### Si l'app n'a pas de hash (app sans hash)

Retourne les informations du joueur via MobCashExternalService :

```json
{
  "UserId": 123456,
  "Name": "Nom du joueur",
  "CurrencyId": 1
}
```

Si le joueur n'est pas trouvé, retourne un objet vide :

```json
{}
```

### Error (400 Bad Request)

#### Validation Error - Paramètres manquants

```json
{
  "details": "Veuillez fournir soit app_id soit app_name."
}
```

#### Validation Error - App non trouvée

```json
{
  "details": "App not found."
}
```

## Exemple de Requête (cURL)

```bash
curl -X POST "https://votre-domaine.com/mobcash/search-user" \
  -H "Content-Type: application/json" \
  -d '{
    "userid": "339966934",
    "app_name": "1xbet"
  }'
```

## Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/mobcash/search-user"
headers = {
    "Content-Type": "application/json"
}
data = {
    "userid": "339966934",
    "app_name": "1xbet"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

