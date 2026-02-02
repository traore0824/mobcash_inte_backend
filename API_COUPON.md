# API Coupon (Utilisateur Non-Admin)

## GET /mobcash/coupon

Récupère la liste des coupons disponibles. Pour les utilisateurs non-admin, seuls les coupons créés dans les dernières 24 heures sont retournés.

**Authentification requise** : Oui (JWT Token)

**Méthode** : GET

**URL** : `/mobcash/coupon`

**Headers** :
```
Authorization: Bearer <token>
```

**Réponse succès (200)** :
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "created_at": "2026-01-31T10:30:00Z",
      "code": "PROMO2026",
      "bet_app": 1,
      "bet_app_details": {
        "id": 1,
        "name": "MonApp",
        "public_name": "Mon Application",
        "logo": "https://example.com/logo.png",
        "url": "https://example.com",
        "created_at": "2026-01-01T00:00:00Z"
      }
    }
  ]
}
```

---

## GET /mobcash/coupon/<id>

Récupère les détails d'un coupon spécifique par son ID.

**Authentification requise** : Oui (JWT Token)

**Méthode** : GET

**URL** : `/mobcash/coupon/<id>`

**Exemple** : `/mobcash/coupon/1`

**Headers** :
```
Authorization: Bearer <token>
```

**Réponse succès (200)** :
```json
{
  "id": 1,
  "created_at": "2026-01-31T10:30:00Z",
  "code": "PROMO2026",
  "bet_app": 1,
  "bet_app_details": {
    "id": 1,
    "name": "MonApp",
    "public_name": "Mon Application",
    "logo": "https://example.com/logo.png",
    "url": "https://example.com",
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

**Réponse erreur (404)** :
```json
{
  "detail": "Not found."
}
```

