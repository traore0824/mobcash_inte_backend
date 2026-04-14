# API Endpoints - Système de Coupons V2 et Crédits Utilisateur

## 🎯 Endpoints Coupons V2

### 1. Liste et Création de Coupons
**GET/POST** `/api/v2/coupons`

**GET** - Liste tous les coupons (avec filtres)
- Query params: `status`, `coupon_type`, `author`, `ordering`
- Réponse: Liste paginée de coupons

**POST** - Créer un nouveau coupon (nécessite `can_publish_coupons=True`)
```json
{
  "coupon_type": "single",
  "code": "ABC123",
  "description": "Description du coupon",
  "odds": "2.50",
  "stake": "1000",
  "date_expiration": "2024-12-31T23:59:59Z",
  "bet_app": 1
}
```

### 2. Détails d'un Coupon
**GET/PUT/DELETE** `/api/v2/coupons/<uuid:pk>`

- **GET**: Récupère les détails d'un coupon
- **PUT**: Modifie un coupon (auteur uniquement)
- **DELETE**: Supprime un coupon (auteur uniquement)

### 3. Voter pour un Coupon
**POST** `/api/v2/coupons/<uuid:pk>/vote`

Nécessite `can_rate_coupons=True`

```json
{
  "vote": "win"  // ou "lose"
}
```

---

## 💰 Endpoints Portefeuille Coupons

### 4. Portefeuille Utilisateur
**GET** `/api/v2/coupon-wallet`

Récupère le solde du portefeuille de l'utilisateur connecté.

### 5. Retrait du Portefeuille
**POST** `/api/v2/coupon-wallet-withdraw`

```json
{
  "amount": "5000"
}
```

### 6. Historique des Paiements
**GET** `/api/v2/coupon-wallet-payouts`

Liste tous les paiements effectués à l'utilisateur.

---

## 💬 Endpoints Commentaires et Notations

### 7. Commentaires d'Auteur
**GET/POST** `/api/v2/author-comments`

**GET** - Liste les commentaires
- Query params: `author`, `coupon`

**POST** - Créer un commentaire
```json
{
  "coupon": "uuid-du-coupon",
  "content": "Excellent coupon!"
}
```

### 8. Détails d'un Commentaire
**GET/PUT/DELETE** `/api/v2/author-comments/<uuid:pk>`

### 9. Notations d'Auteur
**GET/POST** `/api/v2/author-ratings`

**GET** - Liste les notations
- Query params: `user`, `author`

**POST** - Noter un auteur
```json
{
  "author": "uuid-de-l-auteur",
  "rating": 5,
  "comment": "Très bon tipster!"
}
```

---

## 📊 Endpoints Statistiques

### 10. Statistiques Utilisateur
**GET** `/api/v2/user/coupon-stats`

Statistiques de l'utilisateur connecté:
- Nombre de coupons publiés
- Taux de réussite
- Gains totaux
- Crédits restants

### 11. Statistiques d'un Auteur
**GET** `/api/v2/author-stats/<uuid:user_id>`

Statistiques publiques d'un auteur:
- Nombre de coupons
- Taux de réussite
- Note moyenne
- Nombre de followers

---

## 🔐 Permissions Requises

### Publication de Coupons (`can_publish_coupons`)
- Accordée automatiquement après 2 mois d'ancienneté
- Tâche Celery: `grant_coupon_publishing_permissions` (quotidienne à 00h00)

### Notation de Coupons (`can_rate_coupons`)
- Accordée automatiquement après:
  - 1 mois d'ancienneté
  - 15 000 FCFA de dépôts acceptés
- Tâche Celery: `grant_coupon_rating_permissions` (quotidienne à 00h00)

---

## ⚙️ Tâches Celery Automatiques

### 1. Expiration des Coupons
- **Tâche**: `expire_coupons`
- **Fréquence**: Toutes les 30 minutes
- **Action**: Marque les coupons expirés

### 2. Attribution des Crédits Quotidiens
- **Tâche**: `grant_daily_user_credits`
- **Fréquence**: Quotidienne à 00h00
- **Action**: Accorde 3 crédits par jour à chaque utilisateur actif

### 3. Attribution des Permissions de Publication
- **Tâche**: `grant_coupon_publishing_permissions`
- **Fréquence**: Quotidienne à 00h00
- **Action**: Active `can_publish_coupons` pour les utilisateurs éligibles

### 4. Attribution des Permissions de Notation
- **Tâche**: `grant_coupon_rating_permissions`
- **Fréquence**: Quotidienne à 00h00
- **Action**: Active `can_rate_coupons` pour les utilisateurs éligibles

---

## 🚀 Démarrage

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Démarrer le serveur Django
python manage.py runserver

# Démarrer le worker Celery (dans un autre terminal)
celery -A mobcash_inte_backend worker -l info

# Démarrer le beat scheduler Celery (dans un autre terminal)
celery -A mobcash_inte_backend beat -l info
```

---

## ✅ Tests Effectués

Tous les composants ont été testés:
- ✅ Modèles (8 modèles V2)
- ✅ Serializers (8 serializers)
- ✅ Vues (10 vues API)
- ✅ Tâches Celery (4 tâches)
- ✅ URLs (11 endpoints)
- ✅ Migrations (appliquées)
- ✅ Champs utilisateur (can_publish_coupons, can_rate_coupons)

**Aucune erreur 500 détectée !** 🎉
