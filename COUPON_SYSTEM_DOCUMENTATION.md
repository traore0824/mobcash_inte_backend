# Système de Coupons Communautaires — Documentation Complète

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture des modèles](#2-architecture-des-modèles)
3. [Champs User liés aux coupons](#3-champs-user-liés-aux-coupons)
4. [Modèle Setting — configuration du système](#4-modèle-setting--configuration-du-système)
5. [Permissions et règles d'accès](#5-permissions-et-règles-daccès)
6. [Tâches automatiques Celery](#6-tâches-automatiques-celery)
7. [API Endpoints](#7-api-endpoints)
8. [Logique métier détaillée](#8-logique-métier-détaillée)
9. [Serializers](#9-serializers)
10. [Flux complet — exemple pas à pas](#10-flux-complet--exemple-pas-à-pas)

---

## 1. Vue d'ensemble

Le système de coupons communautaires permet à des utilisateurs qualifiés de publier des coupons de paris sportifs, de recevoir des votes (likes/dislikes) d'autres utilisateurs, et de monétiser leur activité via un portefeuille interne.

**Fonctionnalités principales :**
- Publication de coupons (paris simple, combiné, système)
- Système de votes like/dislike avec règles anti-abus
- Commentaires sur les auteurs de coupons (avec réponses imbriquées)
- Portefeuille de gains automatiquement alimenté par les votes
- Retrait des gains via Mobile Money
- Attribution automatique des permissions via des tâches Celery planifiées

---

## 2. Architecture des modèles

### 2.1 Coupon

```python
class Coupon(models.Model):
    COUPON_TYPES = [
        ('single', 'Paris simple'),
        ('combine', 'Paris combiné'),
        ('system', 'Système'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    bet_app = models.ForeignKey(AppName, on_delete=models.CASCADE, blank=True, null=True)
    code = models.CharField(max_length=150, blank=True, null=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='published_coupons', blank=True, null=True)

    # Votes
    likes_count = models.PositiveIntegerField(default=0)
    dislikes_count = models.PositiveIntegerField(default=0)

    # Infos du coupon
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPES, default='combine')
    cote = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)
    match_count = models.PositiveIntegerField(default=1)
    potential_gain = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at']
```

**Champs importants :**
| Champ | Type | Description |
|-------|------|-------------|
| `id` | UUID | Identifiant unique |
| `bet_app` | FK AppName | Application bookmaker liée |
| `code` | CharField | Code du coupon (ex: code promo 1xBet) |
| `author` | FK User | Utilisateur qui a publié le coupon |
| `likes_count` | PositiveInt | Compteur de likes (mis à jour à chaque vote) |
| `dislikes_count` | PositiveInt | Compteur de dislikes |
| `coupon_type` | CharField | `single`, `combine` ou `system` |
| `cote` | Decimal | Cote totale du coupon |
| `match_count` | PositiveInt | Nombre de matchs dans le coupon |
| `potential_gain` | Decimal | Gain potentiel calculé (cote × 10 000 XOF) |


### 2.2 CouponRating

Vote d'un utilisateur sur un coupon spécifique.

```python
class CouponRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    is_like = models.BooleanField(default=True)  # True = Like, False = Dislike
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'coupon']  # 1 vote par user par coupon
```

**Règle clé :** `unique_together = ['user', 'coupon']` — un utilisateur ne peut avoir qu'un seul vote actif par coupon.

---

### 2.3 CouponWallet

Portefeuille de gains de l'auteur, créé automatiquement à l'inscription.

```python
class CouponWallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)        # Solde disponible
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)   # Total historique gagné
    pending_payout = models.DecimalField(max_digits=10, decimal_places=2, default=0) # En attente de paiement
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Création automatique :** via signal `post_save` sur le modèle `User` :

```python
@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        CouponWallet.objects.create(user=instance)
```

---

### 2.4 CouponPayout

Historique des paiements versés à un auteur.

```python
class CouponPayout(models.Model):
    PAYOUT_STATUS = [
        ('pending', 'En attente'),
        ('processing', 'En cours'),
        ('completed', 'Terminé'),
        ('failed', 'Échec'),
        ('cancelled', 'Annulé')
    ]
    PAYOUT_TYPE = [
        ('automatic', 'Automatique - Seuil atteint'),
        ('monthly', 'Paiement mensuel'),
        ('manual', 'Manuel admin')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    wallet = models.ForeignKey(CouponWallet, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_type = models.CharField(max_length=20, choices=PAYOUT_TYPE)
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=50, default='bank_transfer')
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(blank=True)
```

---

### 2.5 CouponWithdrawal

Demande de retrait des gains (avec informations bancaires).

```python
class CouponWithdrawal(models.Model):
    WITHDRAWAL_STATUS = [
        ('pending', 'En attente'),
        ('approved', 'Approuvé'),
        ('rejected', 'Rejeté'),
        ('completed', 'Terminé')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    wallet = models.ForeignKey(CouponWallet, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='pending')
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    account_holder = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
```

---

### 2.6 AuthorComment

Commentaires liés à l'**auteur** du coupon (pas au coupon spécifique). Tous les coupons d'un même auteur partagent les mêmes commentaires. Supporte les réponses imbriquées via `parent`.

```python
class AuthorComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments_written')
    coupon_author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments_received')
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)   # Soft delete
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['coupon_author', '-created_at']),
            models.Index(fields=['parent', '-created_at']),
        ]
```

**Note :** La suppression est un **soft delete** (`is_deleted=True`), le contenu n'est pas effacé de la base.

---

### 2.7 AuthorCouponRating

Like/Dislike lié à l'**auteur** (pas au coupon). Un utilisateur ne peut voter qu'une seule fois par auteur.

```python
class AuthorCouponRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='ratings_given')
    coupon_author = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='ratings_received')
    coupon = models.ForeignKey('Coupon', on_delete=models.CASCADE, related_name='author_ratings', null=True, blank=True)
    is_like = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'coupon_author']  # 1 vote par user par auteur
```

---

## 3. Champs User liés aux coupons

À ajouter dans votre modèle `User` (dans `accounts/models.py`) :

```python
# Système de coupons communautaires
can_publish_coupons = models.BooleanField(default=False)  # Autorisation de publier
can_rate_coupons = models.BooleanField(default=False)     # Autorisation de voter
coupon_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Points accumulés
```

| Champ | Valeur par défaut | Attribué par |
|-------|-------------------|--------------|
| `can_publish_coupons` | `False` | Tâche Celery (2 mois d'ancienneté) ou admin manuellement |
| `can_rate_coupons` | `False` | Tâche Celery (1 mois + 15 000 FCFA de transactions) ou admin |
| `coupon_points` | `0` | Incrémenté à chaque nouveau vote reçu sur un coupon |


---

## 4. Modèle Setting — configuration du système

Champs à ajouter dans votre modèle `Setting` :

```python
# Quotas de création
max_coupons_per_day = models.PositiveIntegerField(default=10)
max_coupons_per_week = models.PositiveIntegerField(default=50)

# Monétisation
enable_coupon_monetization = models.BooleanField(default=False)
minimum_coupon_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
monetization_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)  # Montant gagné PAR VOTE
coupon_rating_points = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

# Mode de paiement
payout_mode = models.CharField(
    max_length=20,
    choices=[('immediate', 'Immédiat'), ('monthly', 'Mensuel')],
    default='monthly'
)
min_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
max_withdrawal_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
auto_approve_withdrawal = models.BooleanField(default=False)
coupon_enable = models.BooleanField(default=False)
```

| Paramètre | Description |
|-----------|-------------|
| `max_coupons_per_day` | Nombre max de coupons qu'un auteur peut publier par jour |
| `max_coupons_per_week` | Nombre max de coupons par semaine |
| `enable_coupon_monetization` | Active/désactive le paiement des auteurs via les votes |
| `minimum_coupon_withdrawal` | Montant minimum pour demander un retrait |
| `monetization_amount` | Montant en XOF crédité à l'auteur pour chaque like reçu (et débité pour chaque dislike) |
| `coupon_enable` | Active/désactive tout le module coupon |

---

## 5. Permissions et règles d'accès

### 5.1 Qui peut publier un coupon ?

Un utilisateur peut publier si **l'une** de ces conditions est vraie :
- `request.user.is_staff == True` (admin)
- `request.user.can_publish_coupons == True`

```python
if not (request.user.is_staff or getattr(request.user, "can_publish_coupons", False)):
    return Response({"error": "Vous n'avez pas l'autorisation de publier des coupons."}, status=403)
```

### 5.2 Qui peut voter (like/dislike) sur un coupon ?

- `request.user.can_rate_coupons == True`
- L'utilisateur ne peut **pas** voter sur son propre coupon
- L'utilisateur ne peut voter qu'**une seule fois par jour par auteur** (sur n'importe lequel de ses coupons)

```python
if not getattr(request.user, 'can_rate_coupons', False):
    return Response({"error": "Vous n'avez pas l'autorisation de noter des coupons"}, status=403)

if coupon.author == request.user:
    return Response({"error": "Vous ne pouvez pas voter sur votre propre coupon"}, status=400)
```

### 5.3 Règle 1 vote/jour/auteur

```python
today = timezone.localdate()
already_voted_today_for_author = CouponRating.objects.filter(
    user=request.user,
    coupon__author=coupon.author,
    created_at__date=today,
).exclude(coupon=coupon).exists()

if already_voted_today_for_author:
    return Response({"error": "Vous avez déjà voté aujourd'hui sur un coupon de cet auteur."}, status=400)
```

### 5.4 Règle 1 coupon par application par jour

Un auteur ne peut créer qu'un seul coupon par application bookmaker par jour :

```python
today = timezone.now().date()
existing_coupon = Coupon.objects.filter(
    author=request.user,
    bet_app=bet_app,
    created_at__date=today
).exists()

if existing_coupon:
    return Response({"error": f"Vous avez déjà créé un coupon pour {bet_app.name} aujourd'hui."}, status=429)
```

### 5.5 Quotas journaliers et hebdomadaires

```python
coupons_today = Coupon.objects.filter(author=user, created_at__date=today).count()
coupons_this_week = Coupon.objects.filter(author=user, created_at__date__gte=week_start).count()

if coupons_today >= settings.max_coupons_per_day:
    # Refus
if coupons_this_week >= settings.max_coupons_per_week:
    # Refus
```

---

## 6. Tâches automatiques Celery

### 6.1 grant_coupon_publishing_permissions

**Fréquence :** Tous les jours à 00h00

**Rôle :** Donne `can_publish_coupons = True` aux utilisateurs actifs ayant au moins **2 mois** d'ancienneté.

```python
@shared_task
def grant_coupon_publishing_permissions():
    two_months_ago = timezone.now() - relativedelta(months=2)
    eligible_users = User.objects.filter(
        date_joined__lte=two_months_ago,
        can_publish_coupons=False,
        is_active=True
    )
    updated_count = eligible_users.update(can_publish_coupons=True)
    return updated_count
```

**Configuration Celery Beat (exemple) :**
```python
CELERY_BEAT_SCHEDULE = {
    'grant-coupon-publishing-permissions': {
        'task': 'betpay.tasks.grant_coupon_publishing_permissions',
        'schedule': crontab(hour=0, minute=0),
    },
}
```

---

### 6.2 grant_coupon_rating_permissions

**Fréquence :** Tous les jours à 00h00

**Rôle :** Donne `can_rate_coupons = True` aux utilisateurs actifs ayant :
- Au moins **1 mois** d'ancienneté
- Au moins **15 000 FCFA** de transactions acceptées (dépôts + retraits)

```python
@shared_task
def grant_coupon_rating_permissions():
    one_month_ago = timezone.now() - relativedelta(months=1)
    eligible_by_age = User.objects.filter(
        date_joined__lte=one_month_ago,
        can_rate_coupons=False,
        is_active=True
    )
    eligible_users = []
    for user in eligible_by_age:
        total_amount = Transaction.objects.filter(
            user_app_id=user.user_app_id,
            status="accept"
        ).aggregate(total=Sum('amount'))['total'] or 0

        if total_amount >= 15000:
            eligible_users.append(user)

    for user in eligible_users:
        user.can_rate_coupons = True
        user.save()

    return len(eligible_users)
```

**Configuration Celery Beat (exemple) :**
```python
CELERY_BEAT_SCHEDULE = {
    'grant-coupon-rating-permissions': {
        'task': 'betpay.tasks.grant_coupon_rating_permissions',
        'schedule': crontab(hour=0, minute=0),
    },
}
```


---

## 7. API Endpoints

### 7.1 Coupons

#### GET /coupon
Liste les coupons du jour en cours.

**Authentification :** Non requise

**Query params :**
| Param | Type | Description |
|-------|------|-------------|
| `bet_app` | UUID | Filtrer par application bookmaker |
| `page` | int | Numéro de page |
| `page_size` | int | Taille de page (max 20) |

**Réponse 200 :**
```json
{
  "count": 5,
  "next": "http://api.example.com/coupon?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "created_at": "2025-01-15T10:30:00Z",
      "code": "PROMO123",
      "bet_app": { "id": "uuid", "name": "1xBet", "public_name": "1xBet" },
      "author": "uuid",
      "author_name": "Jean Dupont",
      "author_first_name": "Jean",
      "author_last_name": "Dupont",
      "author_rating": 4.2,
      "author_coupon_points": 150,
      "coupon_type": "combine",
      "cote": "3.50",
      "match_count": 4,
      "potential_gain": "35000.00",
      "likes": 12,
      "dislikes": 2,
      "user_liked": false,
      "user_disliked": false,
      "average_rating": 4.2,
      "total_ratings": 14,
      "user_rating": null,
      "can_rate": true,
      "comments": [],
      "total_comments": 0
    }
  ]
}
```

---

#### POST /coupon
Créer un nouveau coupon.

**Authentification :** Requise (JWT)

**Condition :** `can_publish_coupons = True` ou `is_staff = True`

**Body :**
```json
{
  "bet_app_id": "uuid-de-l-application",
  "code": "PROMO123",
  "coupon_type": "combine",
  "cote": 3.50,
  "match_count": 4
}
```

| Champ | Requis | Description |
|-------|--------|-------------|
| `bet_app_id` | Oui | UUID de l'application bookmaker |
| `code` | Non | Code du coupon |
| `coupon_type` | Non | `single`, `combine` (défaut), `system` |
| `cote` | Non | Cote totale (doit être > 0) |
| `match_count` | Non | Nombre de matchs (≥ 2 si `combine`) |

**Réponses :**
- `201` — Coupon créé
- `403` — Pas la permission de publier
- `404` — Application bookmaker non trouvée
- `429` — Quota dépassé (jour/semaine) ou coupon déjà créé pour cette app aujourd'hui

---

#### GET /coupon/{pk}
Détail d'un coupon.

**Authentification :** Non requise

---

#### PUT/PATCH/DELETE /coupon/{pk}
Modifier ou supprimer un coupon.

**Authentification :** Admin uniquement (`is_staff`)

---

### 7.2 Votes

#### POST /coupons/{coupon_id}/vote/
Voter sur un coupon (like ou dislike).

**Authentification :** Requise (JWT)

**Condition :** `can_rate_coupons = True`

**Body :**
```json
{
  "vote_type": "like"
}
```

| Valeur `vote_type` | Effet |
|--------------------|-------|
| `"like"` | Like (ou annulation si déjà liké) |
| `"dislike"` | Dislike (ou annulation si déjà disliké) |

**Comportement des votes :**
| Situation | Action |
|-----------|--------|
| Aucun vote existant | Crée le vote |
| Même vote renvoyé (like → like) | Annule le vote (suppression) |
| Vote opposé (like → dislike) | Met à jour le vote |

**Réponse 200 :**
```json
{
  "message": "Vote like enregistré avec succès",
  "coupon": {
    "id": "uuid",
    "likes": 13,
    "dislikes": 2,
    "user_liked": true,
    "user_disliked": false,
    "author_coupon_points": 151
  },
  "amount_earned": "1.00",
  "points_delta": 1
}
```

**Réponses d'erreur :**
- `403` — Pas la permission de voter
- `400` — Vote sur son propre coupon, ou déjà voté aujourd'hui pour cet auteur
- `404` — Coupon non trouvé

---

### 7.3 Portefeuille

#### GET /coupon-wallet
Consulter son portefeuille de gains.

**Authentification :** Requise (JWT)

**Réponse 200 :**
```json
{
  "id": "uuid",
  "user_email": "user@example.com",
  "balance": "45.00",
  "total_earned": "120.00",
  "pending_payout": "0.00",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z",
  "user_stats": {
    "total_coupons": 30,
    "active_coupons": 8,
    "total_likes_received": 120,
    "average_rating": 4.1
  }
}
```

---

#### POST /coupon-wallet-withdraw
Demander un retrait de ses gains.

**Authentification :** Requise (JWT)

**Body :**
```json
{
  "amount": 5000,
  "phone_number": "0701020304",
  "network": "uuid-du-reseau"
}
```

**Validations :**
- `amount` ≥ `setting.minimum_coupon_withdrawal`
- `amount` ≤ `wallet.balance`
- `network` doit exister

**Effet :**
1. Débite `wallet.balance`
2. Crédite `wallet.pending_payout`
3. Crée une `Transaction` de type `coupon_withdrawal`
4. Lance le processus de paiement via l'API du réseau (bpay, barkapay, pal, wave, dgs_pay, connect)

**Réponse 201 :** Données de la transaction créée

---

#### GET /coupon-wallet-payouts
Historique des paiements (admin uniquement).

**Authentification :** Admin (`is_staff`)

---

### 7.4 Statistiques utilisateur

#### GET /user/coupon-stats/
Statistiques de l'utilisateur connecté.

**Authentification :** Requise (JWT)

**Réponse 200 :**
```json
{
  "total_published_coupons": 30,
  "total_ratings_received": 145,
  "average_rating_received": 0,
  "wallet_balance": "45.00",
  "total_earned": "120.00",
  "pending_payouts": "0.00"
}
```

---

### 7.5 Commentaires

#### POST /author-comments/
Créer un commentaire sur l'auteur d'un coupon.

**Authentification :** Requise (JWT)

**Body :**
```json
{
  "coupon_id": "uuid-du-coupon",
  "content": "Excellent pronostiqueur, je recommande !",
  "parent_id": null
}
```

| Champ | Requis | Description |
|-------|--------|-------------|
| `coupon_id` | Oui | UUID du coupon (permet de déduire l'auteur) |
| `content` | Oui | Texte du commentaire (max 5000 chars) |
| `parent_id` | Non | UUID du commentaire parent (pour répondre) |

**Réponse 201 :** Objet `AuthorComment` avec les réponses imbriquées

---

#### GET /author-comments/
Lister les commentaires d'un auteur.

**Authentification :** Requise (JWT)

**Query params :**
| Param | Requis | Description |
|-------|--------|-------------|
| `coupon_author_id` | Oui | UUID de l'auteur |

Retourne uniquement les commentaires de premier niveau (sans parent). Les réponses sont imbriquées dans chaque commentaire.

---

#### PATCH /author-comments/{comment_id}/
Modifier un commentaire.

**Authentification :** Requise (JWT) — auteur du commentaire uniquement

**Body :**
```json
{ "content": "Nouveau contenu" }
```

---

#### DELETE /author-comments/{comment_id}/
Supprimer un commentaire (soft delete).

**Authentification :** Requise (JWT) — auteur du commentaire uniquement

**Réponse 200 :**
```json
{ "message": "Comment deleted successfully" }
```

---

### 7.6 Ratings auteur

#### POST /author-ratings/
Liker ou disliker un auteur (via un coupon).

**Authentification :** Requise (JWT)

**Body :**
```json
{
  "coupon_id": "uuid-du-coupon",
  "is_like": true
}
```

**Comportement :** `update_or_create` — si l'utilisateur a déjà voté pour cet auteur, le vote est mis à jour.

---

#### GET /author-stats/{user_id}/
Statistiques d'un auteur.

**Authentification :** Requise (JWT)

**Réponse 200 :**
```json
{
  "user": {
    "id": "uuid",
    "email": "auteur@example.com",
    "first_name": "Jean",
    "last_name": "Dupont"
  },
  "total_comments": 45,
  "total_likes": 120,
  "total_dislikes": 8,
  "updated_at": "2025-01-15T10:00:00Z"
}
```


---

## 8. Logique métier détaillée

### 8.1 Calcul du `potential_gain`

Calculé automatiquement à la création du coupon :

```python
if cote:
    validated_data["potential_gain"] = cote * 10000  # base de mise : 10 000 XOF
```

---

### 8.2 Calcul de la note de l'auteur (`author_rating`)

La note est calculée dynamiquement dans le serializer, basée sur le ratio likes/total votes de **tous** ses coupons, ramenée sur 5 :

```python
def get_author_rating(self, obj):
    if not obj.author:
        return 0.0
    author_coupons = Coupon.objects.filter(author=obj.author)
    total_likes = sum(coupon.likes_count for coupon in author_coupons)
    total_dislikes = sum(coupon.dislikes_count for coupon in author_coupons)
    total_votes = total_likes + total_dislikes
    if total_votes == 0:
        return 0.0
    success_ratio = total_likes / total_votes
    return round(success_ratio * 5, 2)  # Note sur 5
```

---

### 8.3 Monétisation des votes

Quand un utilisateur vote sur un coupon, si la monétisation est activée (`setting.enable_coupon_monetization = True`) et que l'auteur a `can_publish_coupons = True` :

| Action | Effet sur le wallet de l'auteur |
|--------|--------------------------------|
| Nouveau like | `balance += monetization_amount` |
| Nouveau dislike | `balance -= monetization_amount` |
| Annulation d'un like | `balance -= monetization_amount` |
| Annulation d'un dislike | `balance += monetization_amount` |
| Like → Dislike | `balance -= 2 × monetization_amount` |
| Dislike → Like | `balance += 2 × monetization_amount` |

**Points (`coupon_points`) :**
- Nouveau vote (like ou dislike) : `coupon_points += 1`
- Annulation d'un vote : `coupon_points -= 1`
- Changement like ↔ dislike : pas de changement de points

```python
# Extrait de VoteCouponView
if can_author_receive_coupon_rewards and points_delta != 0:
    author.coupon_points = (author.coupon_points or 0) + points_delta
    author.save(update_fields=["coupon_points"])

if can_author_receive_coupon_rewards and monetization_enabled and adjustment != 0:
    wallet, _created = CouponWallet.objects.get_or_create(user=author)
    wallet.balance += adjustment
    wallet.total_earned += adjustment
    wallet.save(update_fields=["balance", "total_earned"])
```

---

### 8.4 Processus de retrait (`CouponWithdrawalView`)

```
1. Vérifier amount >= setting.minimum_coupon_withdrawal
2. Vérifier amount <= wallet.balance
3. Récupérer le Network (réseau de paiement)
4. Créer Transaction(type_trans="coupon_withdrawal", status="pending")
5. wallet.balance -= amount
6. wallet.pending_payout += amount
7. Lancer le paiement selon network.withdrawal_api :
   - "bpay"     → transfer_bpay_process(transaction)
   - "barkapay" → transfer_barkapay_process(transaction)
   - "pal"      → pal_transfert_process(transaction)
   - "wave"     → wave_transfer_process(transaction)
   - "dgs_pay"  → dgs_payout_process(transaction)
   - autre      → connect_pro_withd_process(transaction)
```

Le webhook de retour du prestataire de paiement appelle `process_coupon_withdrawal_webhook(transaction, success)` pour finaliser.

---

### 8.5 Validation du coupon combiné

```python
if coupon_type == 'combine':
    if match_count is None or match_count < 2:
        raise ValidationError({"match_count": "Un coupon combiné doit avoir au moins 2 matchs."})
```

### 8.6 Unicité du code par application

```python
existing_coupon = Coupon.objects.filter(bet_app=bet_app, code=code).exists()
if existing_coupon:
    raise ValidationError({"code": "Ce code promo existe déjà pour cette application bookmaker."})
```

---

## 9. Serializers

### 9.1 CouponSerializer (champs en lecture)

| Champ | Source | Description |
|-------|--------|-------------|
| `author_name` | `author.get_full_name` | Nom complet de l'auteur |
| `author_rating` | Calculé | Note de l'auteur sur 5 |
| `author_coupon_points` | `author.coupon_points` | Points de l'auteur |
| `user_rating` | Calculé | Vote de l'utilisateur courant (`like`/`dislike`/`null`) |
| `can_rate` | Calculé | Si l'utilisateur courant peut voter |
| `user_liked` | Calculé | `true` si l'utilisateur a liké |
| `user_disliked` | Calculé | `true` si l'utilisateur a disliké |
| `total_ratings` | Calculé | `likes_count + dislikes_count` |
| `average_rating` | Calculé | Note moyenne (ratio likes) |
| `comments` | Calculé | 3 derniers commentaires |
| `total_comments` | Calculé | Nombre total de commentaires |

### 9.2 CouponRatingSerializer (pour voter)

```python
class CouponRatingSerializer(serializers.Serializer):
    vote_type = serializers.ChoiceField(choices=['like', 'dislike'], required=True)
```

### 9.3 CouponWithdrawalSerializer (pour retirer)

```python
class CouponWithdrawalSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    phone_number = serializers.CharField(max_length=20, required=True)
    network = serializers.CharField(required=True)  # UUID du réseau
```

### 9.4 AuthorCommentCreateSerializer (pour commenter)

```python
class AuthorCommentCreateSerializer(serializers.Serializer):
    coupon_id = serializers.UUIDField(required=True)
    content = serializers.CharField(required=True, max_length=5000)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
```

---

## 10. Flux complet — exemple pas à pas

### Scénario : Un utilisateur publie un coupon et reçoit des votes

```
1. [Celery - chaque nuit]
   → grant_coupon_publishing_permissions()
   → Les users avec 2+ mois d'ancienneté reçoivent can_publish_coupons=True

2. [Auteur - POST /coupon]
   Body: { "bet_app_id": "uuid", "code": "WIN123", "coupon_type": "combine", "cote": 3.5, "match_count": 3 }
   → Vérification can_publish_coupons ✓
   → Vérification quota jour/semaine ✓
   → Vérification 1 coupon/app/jour ✓
   → Coupon créé, potential_gain = 3.5 × 10000 = 35000 XOF

3. [Celery - chaque nuit]
   → grant_coupon_rating_permissions()
   → Les users avec 1+ mois et 15000+ FCFA de transactions reçoivent can_rate_coupons=True

4. [Votant - POST /coupons/{id}/vote/]
   Body: { "vote_type": "like" }
   → Vérification can_rate_coupons ✓
   → Vérification pas son propre coupon ✓
   → Vérification pas déjà voté aujourd'hui pour cet auteur ✓
   → CouponRating créé (is_like=True)
   → coupon.likes_count += 1
   → author.coupon_points += 1
   → Si monetization activée : wallet.balance += monetization_amount (ex: 1 XOF)

5. [Auteur - GET /coupon-wallet]
   → Consulte son solde : balance = 1.00 XOF

6. [Auteur - POST /coupon-wallet-withdraw]
   Body: { "amount": 1000, "phone_number": "0701020304", "network": "uuid-mtn" }
   → Vérification amount >= minimum_coupon_withdrawal ✓
   → Vérification amount <= wallet.balance ✓
   → Transaction(type_trans="coupon_withdrawal") créée
   → wallet.balance -= 1000, wallet.pending_payout += 1000
   → Paiement lancé via l'API du réseau MTN

7. [Webhook retour prestataire]
   → process_coupon_withdrawal_webhook(transaction, success=True)
   → Transaction status = "accept"
   → wallet.pending_payout -= 1000
```

---

## Résumé des URLs

| Méthode | URL | Description | Auth |
|---------|-----|-------------|------|
| GET | `/coupon` | Liste coupons du jour | Non |
| POST | `/coupon` | Créer un coupon | JWT + can_publish |
| GET | `/coupon/{pk}` | Détail coupon | Non |
| PUT/DELETE | `/coupon/{pk}` | Modifier/supprimer | Admin |
| POST | `/coupons/{id}/vote/` | Voter sur un coupon | JWT + can_rate |
| GET | `/coupon-wallet` | Mon portefeuille | JWT |
| POST | `/coupon-wallet-withdraw` | Retirer mes gains | JWT |
| GET | `/coupon-wallet-payouts` | Historique paiements | Admin |
| GET | `/user/coupon-stats/` | Mes statistiques | JWT |
| POST | `/author-comments/` | Commenter un auteur | JWT |
| GET | `/author-comments/` | Lister commentaires | JWT |
| PATCH | `/author-comments/{id}/` | Modifier commentaire | JWT (auteur) |
| DELETE | `/author-comments/{id}/` | Supprimer commentaire | JWT (auteur) |
| POST | `/author-ratings/` | Voter pour un auteur | JWT |
| GET | `/author-stats/{user_id}/` | Stats d'un auteur | JWT |
