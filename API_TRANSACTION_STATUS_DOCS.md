# Documentation API

## 1. ChangeTransactionStatusManuelViews
Cet endpoint permet à un administrateur de changer manuellement le statut d'une transaction.

- **URL** : `/mobcash_inte/change-transaction-status-manuel`
- **Méthode** : `POST`
- **Permission** : Admin uniquement (`IsAuthenticated` & `IsAdminUser`)

### Body (JSON)
```json
{
    "reference": "DEPOT-123456789",
    "status": "success"
}
```
* `reference` : La référence unique de la transaction.
* `status` : Le nouveau statut (ex: `success`, `error`, `pending`, `accept`, etc.).

### Réponse (Succès - 200 OK)
Retourne l'objet transaction mis à jour.
```json
{
    "id": 123,
    "reference": "DEPOT-123456789",
    "amount": 5000,
    "status": "success",
    "created_at": "2024-01-01T12:00:00Z",
    "user": { ... },
    ...
}
```

### Réponse (Erreur)
* **404 Not Found** : Si la transaction n'existe pas.
* **400 Bad Request** : Si le statut est manquant.

---

## 2. TransactionStatus
Cet endpoint permet de vérifier le statut d'une transaction directement auprès du fournisseur (ConnectPro ou FeexPay).

- **URL** : `/mobcash_inte/show-transaction-status`
- **Méthode** : `GET`

### Paramètres (Query Params)
* `reference` : La référence de la transaction à vérifier.

Exemple : `/mobcash_inte/show-transaction-status?reference=DEPOT-123456789`

### Réponse (200 OK)
Retourne la réponse brute du fournisseur de paiement (ConnectPro ou FeexPay).

**Exemple ConnectPro :**
```json
{
    "status": "success",
    "message": "Transaction successful",
    "data": { ... }
}
```

**Exemple FeexPay :**
```json
{
    "status": "APPROVED",
    "reference": "...",
    ...
}
```

### Réponse (Erreur)
* **404 Not Found** : Si la transaction introuvable localement.
