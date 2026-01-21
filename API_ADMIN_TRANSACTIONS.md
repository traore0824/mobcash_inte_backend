# Documentation des APIs Admin pour la Gestion des Transactions

## Vue d'ensemble

Ces APIs permettent aux administrateurs de gérer manuellement les transactions (dépôts et retraits) et de suivre leur historique de statuts. Toutes les APIs nécessitent une authentification admin.

**Base URL :** `/api/`

---

## Authentification

Toutes les APIs nécessitent :
- **Permission :** Admin uniquement (`IsAdminUser`)
- **Authentification :** Token d'authentification dans les headers
- **Headers requis :**
  ```
  Authorization: Token <votre_token>
  Content-Type: application/json
  ```

---

## API 1 : Traiter une Transaction

Traite automatiquement une transaction (dépôt ou retrait) selon son type.

### Endpoint

```
POST /api/admin/process-transaction/
```

### Description

Cette API permet de traiter manuellement une transaction existante :
- **Pour les dépôts/rewards :** Appelle automatiquement `webhook_transaction_success()` qui gère :
  - Betpay/Xbet si `transaction.app.hash` existe
  - MobCashExternalService sinon
- **Pour les retraits :** Utilise l'API appropriée selon `transaction.api` :
  - `connect` → `connect_pro_withd_process()`
  - `feexpay` → `feexpay_withdrawall_process()`

### Request Body

```json
{
  "reference": "depot-ABC123XYZ"
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `reference` | string | Oui | Référence unique de la transaction |

### Response Success (200 OK)

```json
{
  "id": 123,
  "reference": "depot-ABC123XYZ",
  "type_trans": "deposit",
  "status": "accept",
  "amount": 5000,
  "user": 45,
  "app": 1,
  "user_app_id": "339966934",
  "network": 2,
  "phone_number": "22912345678",
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
  "fixed_by_admin": false,
  ...
}
```

### Response Errors

#### 404 Not Found
```json
{
  "error": "Transaction non trouvée"
}
```

#### 400 Bad Request
```json
{
  "error": "API de retrait non supportée: unknown_api"
}
```

ou

```json
{
  "error": "Type de transaction non supporté: invalid_type"
}
```

#### 500 Internal Server Error
```json
{
  "error": "Erreur lors du traitement: <détails de l'erreur>"
}
```

### Exemple de Requête (cURL)

```bash
curl -X POST https://votre-domaine.com/api/admin/process-transaction/ \
  -H "Authorization: Token votre_token_admin" \
  -H "Content-Type: application/json" \
  -d '{
    "reference": "depot-ABC123XYZ"
  }'
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/api/admin/process-transaction/"
headers = {
    "Authorization": "Token votre_token_admin",
    "Content-Type": "application/json"
}
data = {
    "reference": "depot-ABC123XYZ"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

---

## API 2 : Changer le Statut d'une Transaction

Change manuellement le statut d'une transaction et enregistre cette modification dans l'historique.

### Endpoint

```
POST /api/admin/update-transaction-status/
```

### Description

Cette API permet de modifier manuellement le statut d'une transaction. Le changement est automatiquement enregistré dans `all_status` avec :
- `source: "admin"`
- `admin_id`: ID de l'admin qui a effectué le changement
- `fixed_by_admin`: Mis à `true`

### Statuts Possibles

Les statuts valides sont définis dans `TRANS_STATUS` :
- `pending` - En attente
- `init_payment` - Une étape sur 2
- `accept` - Accepté
- `error` - Erreur
- `timeouf` - Timeout

### Request Body

```json
{
  "reference": "depot-ABC123XYZ",
  "new_status": "accept"
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `reference` | string | Oui | Référence unique de la transaction |
| `new_status` | string | Oui | Nouveau statut (doit être dans TRANS_STATUS) |

### Response Success (200 OK)

```json
{
  "message": "Statut changé de 'pending' à 'accept'",
  "transaction": {
    "id": 123,
    "reference": "depot-ABC123XYZ",
    "status": "accept",
    "type_trans": "deposit",
    "amount": 5000,
    "fixed_by_admin": true,
    "all_status": [
      {
        "status": "pending",
        "timestamp": "2024-01-15T10:00:00Z",
        "source": "system"
      },
      {
        "status": "accept",
        "timestamp": "2024-01-15T10:30:00Z",
        "source": "admin",
        "admin_id": 5
      }
    ],
    ...
  }
}
```

### Response Errors

#### 400 Bad Request
```json
{
  "new_status": ["\"invalid_status\" n'est pas un choix valide."]
}
```

#### 404 Not Found
```json
{
  "error": "Transaction non trouvée"
}
```

#### 500 Internal Server Error
```json
{
  "error": "Erreur lors du changement de statut: <détails de l'erreur>"
}
```

### Exemple de Requête (cURL)

```bash
curl -X POST https://votre-domaine.com/api/admin/update-transaction-status/ \
  -H "Authorization: Token votre_token_admin" \
  -H "Content-Type: application/json" \
  -d '{
    "reference": "depot-ABC123XYZ",
    "new_status": "accept"
  }'
```

### Exemple de Requête (Python)

```python
import requests

url = "https://votre-domaine.com/api/admin/update-transaction-status/"
headers = {
    "Authorization": "Token votre_token_admin",
    "Content-Type": "application/json"
}
data = {
    "reference": "depot-ABC123XYZ",
    "new_status": "accept"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

---

## API 3 : Consulter l'Historique des Statuts

Récupère l'historique complet des changements de statut d'une transaction.

### Endpoint

```
GET /api/admin/transaction-status-history/
```

### Description

Cette API retourne l'historique complet des statuts d'une transaction depuis sa création, incluant :
- Tous les changements de statut avec timestamps
- La source de chaque changement (system ou admin)
- L'ID de l'admin si le changement a été fait manuellement
- Le statut actuel
- Si la transaction a été fixée par un admin

### Query Parameters

**Critère de recherche :**

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `search` | string | Oui | Terme de recherche qui peut être une référence, un email ou un nom complet |

**Note :** Le paramètre `search` recherche automatiquement dans :
- **Référence de transaction** : Recherche partielle dans la référence (ex: "depot-ABC123XYZ")
- **Email utilisateur** : Recherche partielle dans l'email (User ou TelegramUser)
- **Nom complet** : Recherche partielle dans le nom complet :
  - Si plusieurs mots fournis : premier mot dans `first_name`, reste dans `last_name`
  - Si un seul mot : recherche dans `first_name` ou `last_name`

La recherche est **insensible à la casse** et utilise une logique **OR** (si le terme correspond à n'importe quel champ, la transaction est retournée).

### Response Success (200 OK)

```json
{
  "reference": "depot-ABC123XYZ",
  "current_status": "accept",
  "fixed_by_admin": true,
  "status_history": [
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
      "status": "error",
      "timestamp": "2024-01-15T10:10:00Z",
      "source": "system"
    },
    {
      "status": "accept",
      "timestamp": "2024-01-15T10:30:00Z",
      "source": "admin",
      "admin_id": 5
    }
  ],
  "total_status_changes": 4,
  "user_email": "user@example.com",
  "user_fullname": "Doe John",
  "total_matching_transactions": 1
}
```

**Si plusieurs transactions correspondent :**
```json
{
  "reference": "depot-ABC123XYZ",
  "current_status": "accept",
  "fixed_by_admin": false,
  "status_history": [...],
  "total_status_changes": 3,
  "user_email": "user@example.com",
  "user_fullname": "Doe John",
  "total_matching_transactions": 3,
  "warning": "Attention: 3 transactions trouvées. Affichage de la première (référence: depot-ABC123XYZ)"
}
```

#### Structure de `status_history`

Chaque entrée dans `status_history` contient :

| Champ | Type | Description |
|-------|------|-------------|
| `status` | string | Le statut à ce moment |
| `timestamp` | string (ISO 8601) | Date et heure du changement |
| `source` | string | `"system"` ou `"admin"` |
| `admin_id` | integer | ID de l'admin (seulement si `source == "admin"`) |

### Response Errors

#### 400 Bad Request
```json
{
  "error": "Le paramètre 'search' est requis"
}
```

#### 404 Not Found
```json
{
  "error": "Transaction non trouvée"
}
```

### Exemples de Requêtes

#### Recherche par référence
```bash
curl -X GET "https://votre-domaine.com/api/admin/transaction-status-history/?search=depot-ABC123XYZ" \
  -H "Authorization: Token votre_token_admin"
```

#### Recherche par email
```bash
curl -X GET "https://votre-domaine.com/api/admin/transaction-status-history/?search=user@example.com" \
  -H "Authorization: Token votre_token_admin"
```

#### Recherche par nom complet
```bash
curl -X GET "https://votre-domaine.com/api/admin/transaction-status-history/?search=John Doe" \
  -H "Authorization: Token votre_token_admin"
```

#### Recherche partielle (un seul mot)
```bash
curl -X GET "https://votre-domaine.com/api/admin/transaction-status-history/?search=John" \
  -H "Authorization: Token votre_token_admin"
```

### Exemples de Requêtes (Python)

#### Recherche par référence
```python
import requests

url = "https://votre-domaine.com/api/admin/transaction-status-history/"
headers = {
    "Authorization": "Token votre_token_admin"
}
params = {
    "search": "depot-ABC123XYZ"
}

response = requests.get(url, params=params, headers=headers)
print(response.json())
```

#### Recherche par email
```python
import requests

url = "https://votre-domaine.com/api/admin/transaction-status-history/"
headers = {
    "Authorization": "Token votre_token_admin"
}
params = {
    "search": "user@example.com"
}

response = requests.get(url, params=params, headers=headers)
print(response.json())
```

#### Recherche par nom complet
```python
import requests

url = "https://votre-domaine.com/api/admin/transaction-status-history/"
headers = {
    "Authorization": "Token votre_token_admin"
}
params = {
    "search": "John Doe"
}

response = requests.get(url, params=params, headers=headers)
print(response.json())
```

---

## Codes de Statut HTTP

| Code | Description |
|------|-------------|
| 200 | Succès |
| 400 | Requête invalide (paramètres manquants ou invalides) |
| 401 | Non authentifié |
| 403 | Permission refusée (pas admin) |
| 404 | Transaction non trouvée |
| 500 | Erreur serveur interne |

---

## Notes Importantes

### Traçabilité

- **Tous les changements de statut** sont automatiquement trackés dans `all_status`
- Les changements automatiques (webhooks, traitement système) ont `source: "system"`
- Les changements manuels par admin ont `source: "admin"` + `admin_id`
- Le champ `fixed_by_admin` est mis à `true` uniquement lors d'un changement manuel via l'API 2

### Traitement des Transactions

- **API 1** traite automatiquement selon le type :
  - Dépôts → utilise betpay ou MobCash selon la configuration
  - Retraits → utilise connect ou feexpay selon `transaction.api`
- Si `transaction.api` n'est pas défini pour un retrait, l'API retournera une erreur 400

### Migration Requise

⚠️ **Important :** Avant d'utiliser ces APIs, assurez-vous d'avoir appliqué la migration Django pour les nouveaux champs :
```bash
python manage.py makemigrations
python manage.py migrate
```

### Sécurité

- Toutes les APIs sont protégées par `IsAdminUser`
- Seuls les utilisateurs avec le flag `is_staff=True` peuvent accéder à ces endpoints
- Tous les changements manuels sont tracés avec l'ID de l'admin

---

## Exemples de Cas d'Usage

### Cas 1 : Traiter un dépôt bloqué

```bash
# 1. Traiter la transaction
POST /api/admin/process-transaction/
{
  "reference": "depot-BLOCKED123"
}

# 2. Vérifier l'historique
GET /api/admin/transaction-status-history/?search=depot-BLOCKED123
```

### Cas 2 : Corriger manuellement une transaction en erreur

```bash
# 1. Changer le statut de "error" à "accept"
POST /api/admin/update-transaction-status/
{
  "reference": "depot-ERROR123",
  "new_status": "accept"
}

# 2. Vérifier que fixed_by_admin est maintenant true
GET /api/admin/transaction-status-history/?search=depot-ERROR123
```

### Cas 3 : Auditer une transaction

```bash
# Consulter l'historique complet pour voir tous les changements
GET /api/admin/transaction-status-history/?search=depot-AUDIT123
```

### Cas 4 : Rechercher par email utilisateur

```bash
# Trouver toutes les transactions d'un utilisateur par son email
GET /api/admin/transaction-status-history/?search=user@example.com
```

### Cas 5 : Rechercher par nom complet

```bash
# Trouver les transactions d'un utilisateur par son nom complet
GET /api/admin/transaction-status-history/?search=John Doe
```

### Cas 6 : Recherche partielle

```bash
# Rechercher avec un seul mot (cherche dans référence, email, prénom ou nom)
GET /api/admin/transaction-status-history/?search=John
```

---

## Support

Pour toute question ou problème, contactez l'équipe de développement.

