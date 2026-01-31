# Documentation API - Dépôt, Retrait et Détails de Transaction

## Vue d'ensemble

Documentation des APIs pour créer des transactions (dépôt et retrait) et consulter les détails d'une transaction.

**Base URL :** `/mobcash/`

---

## API 1 : Créer un Dépôt de Transaction

Créer une nouvelle transaction de dépôt pour un utilisateur authentifié.

### Endpoint

```
POST /mobcash/transaction-deposit
```

### Description

Crée une nouvelle transaction de dépôt. La transaction est automatiquement traitée via l'API de dépôt du réseau sélectionné (Connect ou Feexpay). Une référence unique est générée automatiquement.

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Request Body

```json
{
  "amount": 5000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "user_app_id": "339966934",
  "network": 1,
  "source": "mobile"
}
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `amount` | integer | Oui | Montant du dépôt en FCFA |
| `phone_number` | string | Oui | Numéro de téléphone pour le paiement |
| `app` | string (UUID) | Oui | ID de l'application (1xbet, Betway, etc.) |
| `user_app_id` | string | Oui | ID de l'utilisateur sur la plateforme |
| `network` | integer | Oui | ID du réseau (MTN, Moov, Orange, etc.) |
| `source` | string | Oui | Source de la transaction : `mobile`, `web`, `bot` |

### Validations

1. **Montant minimum** : Le montant doit être supérieur ou égal au montant minimum configuré dans les paramètres (`setting.minimum_deposit`)

2. **Protection anti-duplication** : 
   - Si une transaction avec le même `user_app_id`, le même montant et le statut `accept` existe dans les 5 dernières minutes, la création est refusée
   - Un message d'erreur indique le temps restant avant de pouvoir refaire une transaction similaire

### Response Success (201 Created)

```json
{
  "id": 123,
  "reference": "depot-ABC123XYZ",
  "type_trans": "deposit",
  "status": "pending",
  "amount": 5000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "app_details": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "1xbet",
    "image": "https://example.com/1xbet.png",
    "enable": true,
    "minimun_deposit": 1000,
    "max_deposit": 1000000
  },
  "user_app_id": "339966934",
  "network": 1,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com"
  },
  "source": "mobile",
  "api": "connect",
  "created_at": "2024-01-15T10:00:00Z",
  "all_status": [
    {
      "status": "pending",
      "timestamp": "2024-01-15T10:00:00Z",
      "source": "system"
    }
  ],
  "fixed_by_admin": false
}
```

### Response Errors

#### 400 Bad Request - Montant insuffisant
```json
{
  "amount": ["1000 est le montant minimum de depot accepter"]
}
```

#### 400 Bad Request - Transaction récente détectée
```json
{
  "error_time_message": "3 M:45 S"
}
```
**Note :** Le message indique le temps restant (minutes et secondes) avant de pouvoir refaire une transaction similaire.

#### 400 Bad Request - Validation échouée
```json
{
  "amount": ["Ce champ est requis."],
  "phone_number": ["Ce champ est requis."],
  "app": ["Ce champ est requis."],
  "user_app_id": ["Ce champ est requis."],
  "network": ["Ce champ est requis."],
  "source": ["Ce champ est requis."]
}
```

#### 401 Unauthorized
```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

### Comportement

1. **Génération automatique** :
   - Une référence unique est générée avec le préfixe `depot-`
   - L'API de dépôt est déterminée automatiquement selon le réseau (`network.deposit_api`)
   - Le statut initial est `pending`
   - Le statut est tracké dans `all_status`

2. **Traitement automatique** :
   - Après la création, la transaction est automatiquement traitée via `payment_fonction()`
   - Le traitement se fait de manière asynchrone selon l'API configurée

3. **Utilisateur** :
   - L'utilisateur est automatiquement assigné depuis le token d'authentification
   - Le type de transaction est automatiquement défini à `deposit`

---

## API 2 : Créer un Retrait de Transaction

Créer une nouvelle transaction de retrait pour un utilisateur authentifié.

### Endpoint

```
POST /mobcash/transaction-withdrawal
```

### Description

Crée une nouvelle transaction de retrait. La transaction est automatiquement traitée via l'API de retrait du réseau sélectionné (Connect ou Feexpay). Une référence unique est générée automatiquement avec le préfixe `retrait-`.

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Request Body

```json
{
  "amount": 10000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "user_app_id": "339966934",
  "network": 1,
  "withdriwal_code": "CODE123",
  "source": "mobile"
}
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `amount` | integer | Oui | Montant du retrait en FCFA |
| `phone_number` | string | Oui | Numéro de téléphone pour recevoir le paiement |
| `app` | string (UUID) | Oui | ID de l'application (1xbet, Betway, etc.) |
| `user_app_id` | string | Oui | ID de l'utilisateur sur la plateforme |
| `network` | integer | Oui | ID du réseau (MTN, Moov, Orange, etc.) |
| `withdriwal_code` | string | Oui | Code de retrait fourni par la plateforme |
| `source` | string | Oui | Source de la transaction : `mobile`, `web`, `bot` |

### Response Success (201 Created)

```json
{
  "id": 124,
  "reference": "retrait-ABC123XYZ",
  "type_trans": "withdrawal",
  "status": "pending",
  "amount": 10000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "app_details": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "1xbet",
    "image": "https://example.com/1xbet.png",
    "enable": true,
    "minimun_with": 500,
    "max_win": 500000
  },
  "user_app_id": "339966934",
  "network": 1,
  "withdriwal_code": "CODE123",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com"
  },
  "source": "mobile",
  "api": "connect",
  "created_at": "2024-01-15T10:00:00Z",
  "all_status": [
    {
      "status": "pending",
      "timestamp": "2024-01-15T10:00:00Z",
      "source": "system"
    }
  ],
  "fixed_by_admin": false
}
```

### Champs retournés (principaux)

| Champ | Type | Description |
|-------|------|-------------|
| `id` | integer | ID de la transaction |
| `reference` | string | Référence unique générée automatiquement (préfixe: `retrait-`) |
| `type_trans` | string | Type de transaction : `withdrawal` |
| `status` | string | Statut actuel : `pending`, `init_payment`, `accept`, `error` |
| `amount` | integer | Montant en FCFA |
| `phone_number` | string | Numéro de téléphone |
| `app` | string (UUID) | ID de l'application |
| `app_details` | object | Détails complets de l'application |
| `user_app_id` | string | ID de l'utilisateur sur la plateforme |
| `network` | integer | ID du réseau |
| `withdriwal_code` | string | Code de retrait |
| `user` | object | Informations de l'utilisateur |
| `source` | string | Source de la transaction |
| `api` | string | API utilisée : `connect` ou `feexpay` (déterminé automatiquement selon le réseau) |
| `created_at` | string (ISO 8601) | Date de création |
| `all_status` | array | Historique des statuts |
| `fixed_by_admin` | boolean | Si corrigé par admin |

### Response Errors

#### 400 Bad Request - Validation échouée
```json
{
  "amount": ["Ce champ est requis."],
  "phone_number": ["Ce champ est requis."],
  "app": ["Ce champ est requis."],
  "user_app_id": ["Ce champ est requis."],
  "network": ["Ce champ est requis."],
  "withdriwal_code": ["Ce champ est requis."],
  "source": ["Ce champ est requis."]
}
```

#### 401 Unauthorized
```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

### Comportement

1. **Génération automatique** :
   - Une référence unique est générée avec le préfixe `retrait-`
   - L'API de retrait est déterminée automatiquement selon le réseau (`network.withdrawal_api`)
   - Le statut initial est `pending`
   - Le statut est tracké dans `all_status`

2. **Traitement automatique** :
   - Après la création, la transaction est automatiquement traitée via `payment_fonction()`
   - Le traitement se fait de manière asynchrone selon l'API configurée

3. **Utilisateur** :
   - L'utilisateur est automatiquement assigné depuis le token d'authentification
   - Le type de transaction est automatiquement défini à `withdrawal`

---

## API 3 : Consulter les Détails d'une Transaction

Récupère les détails complets d'une transaction spécifique par son ID ou sa référence.

### Endpoint

```
GET /mobcash/transaction-detail
```

### Description

Récupère tous les détails d'une transaction spécifique. Les utilisateurs non-admin ne peuvent voir que leurs propres transactions.

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Query Parameters

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | integer | Optionnel* | ID de la transaction |
| `reference` | string | Optionnel* | Référence de la transaction |

**Note :** Au moins un des deux paramètres (`id` ou `reference`) doit être fourni.

### Response Success (200 OK)

```json
{
  "id": 123,
  "reference": "depot-ABC123XYZ",
  "type_trans": "deposit",
  "status": "accept",
  "amount": 5000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "app_details": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "1xbet",
    "image": "https://example.com/1xbet.png",
    "enable": true
  },
  "user_app_id": "339966934",
  "network": 1,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com"
  },
  "source": "mobile",
  "api": "connect",
  "public_id": "PUB123456",
  "created_at": "2024-01-15T10:00:00Z",
  "validated_at": "2024-01-15T10:05:00Z",
  "all_status": [
    {
      "status": "pending",
      "timestamp": "2024-01-15T10:00:00Z",
      "source": "system"
    },
    {
      "status": "init_payment",
      "timestamp": "2024-01-15T10:02:00Z",
      "source": "system"
    },
    {
      "status": "accept",
      "timestamp": "2024-01-15T10:05:00Z",
      "source": "system"
    }
  ],
  "fixed_by_admin": false
}
```

### Champs retournés (tous les champs de la transaction)

Tous les champs de la transaction sont retournés, incluant :
- Informations de base (id, reference, type_trans, status, amount)
- Informations de contact (phone_number)
- Informations d'application (app, app_details, user_app_id)
- Informations de réseau (network)
- Informations utilisateur (user)
- Informations de traitement (api, public_id, source)
- Dates (created_at, validated_at)
- Historique (all_status)
- Métadonnées (fixed_by_admin)

### Response Errors

#### 400 Bad Request - Paramètres manquants
```json
{
  "error": "Le paramètre 'id' ou 'reference' est requis"
}
```

#### 404 Not Found - Transaction non trouvée
```json
{
  "error": "Transaction non trouvée"
}
```

#### 403 Forbidden - Accès refusé
```json
{
  "error": "Vous n'avez pas accès à cette transaction"
}
```
**Note :** Les utilisateurs non-admin ne peuvent voir que leurs propres transactions.

#### 401 Unauthorized
```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

### Exemple de Requête (cURL)

```bash
# Par ID
curl -X GET "https://votre-domaine.com/mobcash/transaction-detail?id=123" \
  -H "Authorization: Bearer votre_access_token"

# Par référence
curl -X GET "https://votre-domaine.com/mobcash/transaction-detail?reference=depot-ABC123XYZ" \
  -H "Authorization: Bearer votre_access_token"
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/mobcash/transaction-detail"
headers = {
    "Authorization": "Bearer votre_access_token"
}

# Par ID
params = {"id": 123}
response = requests.get(url, params=params, headers=headers)
print(response.json())

# Par référence
params = {"reference": "depot-ABC123XYZ"}
response = requests.get(url, params=params, headers=headers)
print(response.json())
```

---

## Codes de Statut HTTP

| Code | Description |
|------|-------------|
| 200 | Succès |
| 201 | Créé avec succès (POST) |
| 400 | Requête invalide (validation échouée) |
| 401 | Non authentifié (token manquant ou invalide) |
| 403 | Permission refusée |
| 404 | Transaction non trouvée |

---

## Flux de Traitement d'une Transaction

### Pour un Dépôt

1. **Création** : L'utilisateur appelle `POST /mobcash/transaction-deposit`
2. **Réponse immédiate** : La transaction est créée avec le statut `pending`
3. **Traitement automatique** : `payment_fonction()` est appelé pour traiter le paiement
4. **Vérification** : L'utilisateur peut appeler `GET /mobcash/transaction-detail` pour voir les détails
5. **Webhook** : L'API externe notifie le système via webhook pour mettre à jour le statut final

### Pour un Retrait

1. **Création** : L'utilisateur appelle `POST /mobcash/transaction-withdrawal`
2. **Réponse immédiate** : La transaction est créée avec le statut `pending`
3. **Traitement automatique** : `payment_fonction()` est appelé pour traiter le retrait
4. **Vérification** : L'utilisateur peut appeler `GET /mobcash/transaction-detail` pour voir les détails
5. **Webhook** : L'API externe notifie le système via webhook pour mettre à jour le statut final

---

## Exemples de Cas d'Usage

### Cas 1 : Créer un dépôt MTN pour 1xbet

```bash
POST /mobcash/transaction-deposit
Headers: Authorization: Bearer <access_token>
{
  "amount": 10000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "user_app_id": "339966934",
  "network": 1,
  "source": "mobile"
}
```

### Cas 2 : Créer un retrait MTN

```bash
POST /mobcash/transaction-withdrawal
Headers: Authorization: Bearer <access_token>
{
  "amount": 5000,
  "phone_number": "22912345678",
  "app": "550e8400-e29b-41d4-a716-446655440000",
  "user_app_id": "339966934",
  "network": 1,
  "withdriwal_code": "CODE123",
  "source": "mobile"
}
```

### Cas 3 : Voir les détails d'une transaction

```bash
GET /mobcash/transaction-detail?reference=depot-ABC123XYZ
Headers: Authorization: Bearer <access_token>
```

### Cas 4 : Gérer l'erreur de transaction récente

Si une transaction similaire existe dans les 5 dernières minutes, l'API retourne :
```json
{
  "error_time_message": "2 M:30 S"
}
```
L'application doit afficher un message à l'utilisateur indiquant qu'il doit attendre 2 minutes et 30 secondes.

---

## Support

Pour toute question ou problème, contactez l'équipe de développement.
