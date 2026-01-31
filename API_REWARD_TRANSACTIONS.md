# Documentation API - Reward

## API 1 : Récupérer le Solde Reward

### Endpoint

```
GET /mobcash/reward
```

### Description

Récupère le solde Reward de l'utilisateur authentifié. Retourne le solde Reward total, la somme des bonus disponibles et le total disponible.

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Response Success (200 OK)

```json
{
  "reward_amount": 5000.0,
  "available_bonus_total": 10000.0,
  "total_available": 15000.0
}
```

### Champs de la réponse

| Champ | Type | Description |
|-------|------|-------------|
| `reward_amount` | float | Solde Reward total de l'utilisateur (Reward.amount) |
| `available_bonus_total` | float | Somme de tous les bonus disponibles (non utilisés) |
| `total_available` | float | Total disponible (reward_amount + available_bonus_total) |

### Response Errors

#### 401 Unauthorized

```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

### Exemple de Requête (cURL)

```bash
curl -X GET "https://votre-domaine.com/mobcash/reward" \
  -H "Authorization: Bearer votre_access_token"
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/mobcash/reward"
headers = {
    "Authorization": "Bearer votre_access_token"
}

response = requests.get(url, headers=headers)
print(response.json())
```

---

## API 2 : Utiliser Tout le Solde Reward (Transaction)

### Endpoint

```
POST /mobcash/transaction-reward
```

### Description

Utilise **automatiquement tout le solde Reward disponible** (somme de tous les bonus non utilisés) pour créer une transaction de dépôt sur la plateforme. Cette API retire tout l'argent disponible dans le Reward de l'utilisateur et marque tous les bonus comme utilisés.

**Le système calcule automatiquement le montant total disponible - aucun montant n'est requis.**

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Request Body

```json
{
  "user_app_id": "339966934",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "source": "mobile"
}
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `user_app_id` | string | Oui | ID de l'utilisateur sur la plateforme (1xbet, Betway, etc.) |
| `app` | UUID | Oui | ID de l'application (plateforme) |
| `source` | string | Oui | Source de la transaction : `mobile`, `web`, `bot` |

**Note :** Aucun montant n'est requis. Le système calcule automatiquement le montant total des bonus disponibles.

### Response Success (201 Created)

```json
{
  "id": 125,
  "reference": "depot-ABC123XYZ",
  "amount": 15000,
  "type_trans": "reward",
  "status": "accept",
  "user_app_id": "339966934",
  "app": {...},
  "validated_at": "2024-01-15T10:30:00Z",
  // ... autres champs de TransactionDetailsSerializer
}
```

### Response Errors

#### 400 Bad Request - Aucun bonus disponible

```json
{
  "details": "Vous n'avez aucun bonus disponible à utiliser."
}
```

#### 400 Bad Request - Transaction déjà traitée

```json
{
  "error": "Transaction déjà traitée"
}
```

#### 400 Bad Request - Échec de l'API

```json
{
  "error": "Échec du traitement de la transaction",
  "details": {...}
}
```

#### 500 Internal Server Error

```json
{
  "error": "Erreur lors du traitement",
  "details": "Message d'erreur détaillé"
}
```

#### 500 Internal Server Error - Configuration manquante

```json
{
  "error": "Configuration système non trouvée"
}
```

### Exemple de Requête (cURL)

```bash
curl -X POST "https://votre-domaine.com/mobcash/transaction-reward" \
  -H "Authorization: Bearer votre_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_app_id": "339966934",
    "app": "550e8400-e29b-41d4-a716-446655440000",
    "source": "mobile"
  }'
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/mobcash/transaction-reward"
headers = {
    "Authorization": "Bearer votre_access_token",
    "Content-Type": "application/json"
}
data = {
    "user_app_id": "339966934",
    "app": "550e8400-e29b-41d4-a716-446655440000",
    "source": "mobile"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### Comportement

1. **Calcul automatique** : Le système calcule automatiquement la somme de tous les bonus non utilisés (`bonus_with=False`, `bonus_delete=False`)
2. **Vérification** : Si aucun bonus disponible, retourne une erreur 400
3. **Création** : Crée une transaction de type `"reward"` avec le montant total calculé
4. **Traitement direct** : Appelle directement l'API de dépôt (pas de webhook) :
   - Si `app.hash` existe → `servculAPI.recharge_account()`
   - Sinon → `MobCashExternalService().create_deposit()`
5. **Marquage** : Si succès (`Success == True`), marque **tous** les bonus comme utilisés (`bonus_with=True`)
6. **Statut** : 
   - Si succès → `status="accept"` + notifications
   - Si échec → `status="error"` (les bonus restent disponibles)

### Sécurité

- **Transaction atomique** : Tout le processus est dans une transaction atomique
- **Verrouillage** : Utilise `select_for_update()` pour éviter les race conditions
- **Vérification de statut** : Vérifie que la transaction n'est pas déjà traitée avant de procéder

### Note

Pour connaître le solde Reward disponible avant de créer une transaction, utilisez `GET /mobcash/reward`.

---

## Support

Pour toute question ou problème, contactez l'équipe de développement.
