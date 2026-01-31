# Documentation API - Transactions Reward

## API 1 : Utiliser Tout le Solde Reward (RewardTransactionViews)

### Endpoint

```
POST /mobcash/transaction-reward
```

### Description

Utilise **automatiquement tout le solde Reward disponible** (somme de tous les bonus non utilisés) pour créer une transaction de dépôt sur la plateforme. Cette API retire tout l'argent disponible dans le Reward de l'utilisateur et marque tous les bonus comme utilisés.

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

**Note :** Aucun montant n'est requis. Le système utilise automatiquement tout le solde Reward disponible.

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

1. **Calcul automatique** : Le système calcule automatiquement la somme de tous les bonus non utilisés
2. **Vérification** : Si aucun bonus disponible, retourne une erreur 400
3. **Création** : Crée une transaction avec le montant total calculé
4. **Traitement direct** : Appelle directement l'API de dépôt (pas de webhook)
5. **Marquage** : Si succès, marque **tous** les bonus comme utilisés (`bonus_with=True`)
6. **Statut** : Si succès → `status="accept"`, si échec → `status="error"` (bonus restent disponibles)

---

## API 2 : Créer une Transaction Reward avec Montant (CreateBonusDepositTransactionViews)

### Endpoint

```
POST /mobcash/transaction-bonus
```

### Description

Crée une transaction de type "reward" avec un montant spécifique. Cette API utilise les bonus disponibles de l'utilisateur et les marque comme utilisés. Le montant doit respecter le minimum configuré dans les settings.

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Request Body

```json
{
  "amount": 10000,
  "user_app_id": "339966934",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "source": "mobile"
}
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `amount` | integer | Oui | Montant de la transaction en FCFA |
| `user_app_id` | string | Oui | ID de l'utilisateur sur la plateforme |
| `app` | UUID | Oui | ID de l'application (plateforme) |
| `source` | string | Oui | Source de la transaction : `mobile`, `web`, `bot` |

### Validations

1. **Montant minimum** : Le montant doit être >= `setting.reward_mini_withdrawal`
2. **Bonus disponibles** : L'utilisateur doit avoir suffisamment de bonus disponibles
3. **Reward disponible** : Le solde Reward doit être >= au montant demandé
4. **Anti-duplication** : Pas de transaction identique acceptée dans les 5 dernières minutes

### Response Success (201 Created)

```json
{
  "id": 126,
  "reference": "depot-DEF456UVW",
  "amount": 10000,
  "type_trans": "reward",
  "status": "accept",
  "user_app_id": "339966934",
  "app": {...},
  "validated_at": "2024-01-15T10:35:00Z",
  // ... autres champs de TransactionDetailsSerializer
}
```

### Response Errors

#### 400 Bad Request - Montant insuffisant

```json
{
  "amount": "5000 est le montant minimum de bonus pour une operation accepter"
}
```

#### 400 Bad Request - Transaction récente

```json
{
  "error_time_message": "2 M:30 S"
}
```

**Note :** L'utilisateur doit attendre le temps indiqué avant de refaire une transaction similaire.

#### 400 Bad Request - Solde Reward insuffisant

```json
{
  "amount": "5000 est le montant minimum de bonus pour une operation accepter"
}
```

#### 401 Unauthorized

```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

### Exemple de Requête (cURL)

```bash
curl -X POST "https://votre-domaine.com/mobcash/transaction-bonus" \
  -H "Authorization: Bearer votre_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 10000,
    "user_app_id": "339966934",
    "app": "550e8400-e29b-41d4-a716-446655440000",
    "source": "mobile"
  }'
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/mobcash/transaction-bonus"
headers = {
    "Authorization": "Bearer votre_access_token",
    "Content-Type": "application/json"
}
data = {
    "amount": 10000,
    "user_app_id": "339966934",
    "app": "550e8400-e29b-41d4-a716-446655440000",
    "source": "mobile"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

### Comportement

1. **Validation** : Vérifie le montant minimum, les bonus disponibles et le solde Reward
2. **Anti-duplication** : Vérifie qu'il n'y a pas de transaction identique dans les 5 dernières minutes
3. **Création** : Crée une transaction de type "reward" avec le montant spécifié
4. **Traitement** : Appelle `webhook_transaction_success()` qui traite la transaction directement
5. **Marquage** : Marque les bonus comme utilisés et met le solde Reward à 0

---

## Différences entre les deux APIs

| Caractéristique | API 1 (transaction-reward) | API 2 (transaction-bonus) |
|----------------|----------------------------|--------------------------|
| **Montant** | Automatique (tout le solde) | Spécifié par l'utilisateur |
| **Validation** | Vérifie seulement si bonus > 0 | Vérifie montant minimum, bonus, Reward |
| **Anti-duplication** | Non | Oui (5 minutes) |
| **Traitement** | Appel direct API | Via `webhook_transaction_success()` |
| **Marquage bonus** | Tous les bonus | Bonus utilisés selon montant |
| **Solde Reward** | Non modifié directement | Mis à 0 après utilisation |

---

## Support

Pour toute question ou problème, contactez l'équipe de développement.

