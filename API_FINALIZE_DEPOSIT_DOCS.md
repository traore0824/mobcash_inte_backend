# API Documentation: Finalize Deposit Transaction

## Endpoint
**POST** `/finalize-transaction`

## Description
Cette API permet de finaliser manuellement une transaction de dépôt en attente. Elle est utilisée pour compléter des transactions qui n'ont pas été automatiquement validées, en effectuant le rechargement du compte utilisateur sur l'application cible et en mettant à jour le statut de la transaction.

## Authentification
- **Requis**: Oui
- **Type**: Token d'authentification
- **Permission**: Administrateur uniquement (`IsAdminUser`)

## Headers
```http
Authorization: Token <votre_token_admin>
Content-Type: application/json
```

## Request Body

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `reference` | string | Oui | La référence unique de la transaction à finaliser |

### Exemple de requête
```json
{
  "reference": "TXN123456789"
}
```

## Réponses

### Succès (200 OK)
Retourne les détails complets de la transaction finalisée.

#### Structure de la réponse
```json
{
  "id": 123,
  "reference": "TXN123456789",
  "amount": "5000.00",
  "status": "accept",
  "user": {
    "id": 456,
    "username": "user@example.com",
    "phone": "+221771234567"
  },
  "app": {
    "id": 1,
    "name": "1xBet",
    "hash": "app_hash_value"
  },
  "user_app_id": "USER123",
  "mobcash_response": "{...}",
  "created_at": "2026-02-10T10:30:00Z",
  "updated_at": "2026-02-10T11:00:00Z"
}
```

### Erreur - Transaction non trouvée (404 NOT FOUND)
La transaction avec la référence fournie n'existe pas ou a déjà été acceptée.

```json
{
  "detail": "Not found."
}
```

### Erreur - Non autorisé (401 UNAUTHORIZED)
L'utilisateur n'est pas authentifié.

```json
{
  "detail": "Authentication credentials were not provided."
}
```

### Erreur - Permission refusée (403 FORBIDDEN)
L'utilisateur n'a pas les permissions d'administrateur.

```json
{
  "detail": "You do not have permission to perform this action."
}
```

## Comportement

### Processus de finalisation

1. **Recherche de la transaction**
   - Recherche la transaction par référence
   - Exclut les transactions déjà acceptées (`status != "accept"`)

2. **Initialisation de l'API MobCash**
   - Initialise le service API selon l'application cible

3. **Rechargement du compte**
   - **Si l'application a un hash** (`app.hash` existe):
     - Utilise `servculAPI.recharge_account()` pour recharger le compte
     - Paramètres: montant et ID utilisateur de l'application
   
   - **Si l'application n'a pas de hash**:
     - Utilise `MobCashExternalService().create_deposit()` pour créer le dépôt

4. **Validation de la réponse**
   - Vérifie si `response.data.Success == True`
   - Si succès:
     - Met à jour le statut de la transaction à `"accept"`
     - Enregistre la réponse MobCash
     - Déclenche une tâche asynchrone pour vérifier le solde (`check_solde.delay()`)
     - Envoie une notification push à l'utilisateur

5. **Retour de la réponse**
   - Retourne les détails complets de la transaction (sérialisée)

## Effets secondaires

### Actions déclenchées
1. **Mise à jour de la transaction**
   - `status` → `"accept"`
   - `mobcash_response` → Réponse de l'API

2. **Tâche asynchrone**
   - `check_solde.delay(transaction_id)` - Vérifie le solde après finalisation

3. **Notification utilisateur**
   - **Titre**: "Opération réussie avec succès"
   - **Contenu**: "Vous avez effectué un dépôt de {montant} FCFA sur votre compte {nom_app}"

## Logs
Les réponses de l'API sont enregistrées dans le logger `connect_pro_logger`:
```
Reponse de l'api de {app.name}: {response}
```

## Cas d'usage

### Exemple 1: Finaliser une transaction en attente
```bash
curl -X POST https://api.example.com/finalize-transaction \
  -H "Authorization: Token votre_token_admin" \
  -H "Content-Type: application/json" \
  -d '{
    "reference": "TXN123456789"
  }'
```

### Exemple 2: Utilisation avec Python
```python
import requests

url = "https://api.example.com/finalize-transaction"
headers = {
    "Authorization": "Token votre_token_admin",
    "Content-Type": "application/json"
}
data = {
    "reference": "TXN123456789"
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

## Notes importantes

> [!WARNING]
> Cette API ne peut finaliser que les transactions qui ne sont **pas déjà acceptées**. Les transactions avec `status = "accept"` sont automatiquement exclues.

> [!IMPORTANT]
> Seuls les administrateurs peuvent utiliser cette API. Assurez-vous d'avoir les permissions appropriées.

> [!NOTE]
> Le processus de rechargement varie selon que l'application cible possède un hash ou non. Les deux méthodes sont gérées automatiquement par l'API.

## Dépendances

### Services externes
- **MobCash API**: Pour le rechargement des comptes
- **MobCashExternalService**: Pour les applications sans hash

### Tâches asynchrones
- `check_solde`: Vérifie le solde après finalisation

### Modèles
- `Transaction`: Modèle de transaction principal
- `TransactionDetailsSerializer`: Sérialiseur pour la réponse

## Statuts de transaction

| Statut | Description |
|--------|-------------|
| `pending` | Transaction en attente |
| `accept` | Transaction acceptée et finalisée |
| `reject` | Transaction rejetée |
| `cancel` | Transaction annulée |

## Codes d'erreur possibles

| Code | Description | Solution |
|------|-------------|----------|
| 404 | Transaction non trouvée ou déjà acceptée | Vérifier la référence de la transaction |
| 401 | Non authentifié | Fournir un token d'authentification valide |
| 403 | Permission refusée | Utiliser un compte administrateur |
| 500 | Erreur serveur | Vérifier les logs du serveur |

## Changelog

### Version actuelle
- Finalisation manuelle des transactions de dépôt
- Support des applications avec et sans hash
- Notifications push automatiques
- Vérification asynchrone du solde
