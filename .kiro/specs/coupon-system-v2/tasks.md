# Plan d'implémentation : Coupon System V2

## Vue d'ensemble

Implémentation du système de coupons communautaires V2 dans l'application Django existante `mobcash_inte`. Les tâches suivent une progression incrémentale : modèles → migrations → serializers → vues → routes → tâches Celery → admin.

## Tâches

- [x] 1. Étendre les modèles existants (User et Setting)
  - Ajouter `can_publish_coupons`, `can_rate_coupons`, `coupon_points` dans `accounts/models.py` sur le modèle `User`
  - Ajouter les 11 champs coupon dans `mobcash_inte/models.py` sur le modèle `Setting` : `max_coupons_per_day`, `max_coupons_per_week`, `enable_coupon_monetization`, `minimum_coupon_withdrawal`, `monetization_amount`, `coupon_rating_points`, `payout_mode`, `min_withdrawal`, `max_withdrawal_monthly`, `auto_approve_withdrawal`, `coupon_enable`
  - _Requirements: 1.1, 1.2, 2.4, 4.1, 5.1_

- [x] 2. Créer les nouveaux modèles dans `mobcash_inte/models.py`
  - [x] 2.1 Créer `CouponV2` avec les champs : `id` (UUID), `created_at`, `bet_app` (FK AppName), `code`, `author` (FK User), `likes_count`, `dislikes_count`, `coupon_type` (single/combine/system), `cote`, `match_count`, `potential_gain`
    - Ajouter `class Meta: ordering = ['-created_at']`
    - _Requirements: 2.1, 2.2, 2.3, 2.5_
  - [x] 2.2 Créer `CouponRatingV2` avec `id` (UUID), `user` (FK), `coupon` (FK CouponV2), `is_like`, `created_at` et `unique_together = ['user', 'coupon']`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 2.3 Créer `CouponWallet` avec `id` (UUID), `user` (OneToOne), `balance`, `total_earned`, `pending_payout`, `created_at`, `updated_at`
    - _Requirements: 4.1, 4.2, 5.2, 5.3_
  - [x] 2.4 Créer `CouponPayout` avec `id` (UUID), `user` (FK), `wallet` (FK), `amount`, `payout_type` (automatic/monthly/manual), `status` (pending/processing/completed/failed/cancelled), `processed_at`, `created_at`, `payment_method`, `transaction_id`, `notes`
    - _Requirements: 5.3_
  - [x] 2.5 Créer `CouponWithdrawal` avec `id` (UUID), `user` (FK), `wallet` (FK), `amount`, `status` (pending/approved/rejected/completed), `bank_name`, `account_number`, `account_holder`, `created_at`, `processed_at`, `admin_notes`
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 2.6 Créer `AuthorComment` avec `id` (UUID), `author` (FK User, related_name='comments_written'), `coupon_author` (FK User, related_name='comments_received'), `coupon` (FK CouponV2, null/blank), `content`, `parent` (FK self, null/blank, related_name='replies'), `created_at`, `updated_at`, `is_deleted`, `deleted_at`
    - Ajouter les index sur `(coupon_author, -created_at)` et `(parent, -created_at)`
    - _Requirements: 6.1, 6.2_
  - [x] 2.7 Créer `AuthorCouponRating` avec `id` (UUID), `user` (FK, related_name='ratings_given'), `coupon_author` (FK, related_name='ratings_received'), `coupon` (FK CouponV2, null/blank), `is_like`, `created_at`, `updated_at` et `unique_together = ['user', 'coupon_author']`
    - _Requirements: 7.1, 7.2_

- [x] 3. Créer le signal post_save dans `mobcash_inte/signals.py`
  - Créer le fichier `mobcash_inte/signals.py` avec le signal `post_save` sur `User` qui crée automatiquement un `CouponWallet` à la création d'un utilisateur
  - Connecter le signal dans `mobcash_inte/apps.py` via `ready()`
  - _Requirements: 4.1_

- [x] 4. Créer et appliquer les migrations Django
  - Générer les migrations : `python manage.py makemigrations`
  - Appliquer les migrations : `python manage.py migrate`
  - _Requirements: 1.1, 1.2, 2.1–2.7_

- [x] 5. Créer les serializers dans `mobcash_inte/serializers.py`
  - [x] 5.1 Créer `CouponV2Serializer` (lecture) et `CouponV2CreateSerializer` (écriture) avec validation de `match_count >= 2` pour les coupons combinés et calcul automatique de `potential_gain = cote * 10000`
    - _Requirements: 2.1, 2.2_
  - [ ]* 5.2 Écrire les tests unitaires pour `CouponV2CreateSerializer`
    - Tester la validation `match_count < 2` pour type combine
    - Tester le calcul de `potential_gain`
    - _Requirements: 2.1, 2.2_
  - [x] 5.3 Créer `CouponRatingV2Serializer` pour les votes
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 5.4 Créer `CouponWalletSerializer`, `CouponPayoutSerializer`, `CouponWithdrawalSerializer`
    - _Requirements: 4.1, 5.1, 5.2, 5.3_
  - [x] 5.5 Créer `AuthorCommentSerializer` avec gestion des réponses imbriquées (champ `replies` en lecture seule)
    - _Requirements: 6.1, 6.2_
  - [x] 5.6 Créer `AuthorCouponRatingSerializer`
    - _Requirements: 7.1, 7.2_

- [x] 6. Implémenter les vues dans `mobcash_inte/views.py`
  - [x] 6.1 Implémenter `CouponV2View` (ListCreateAPIView) avec :
    - `GET` : liste les coupons du jour (public)
    - `POST` : vérifie `can_publish_coupons` ou `is_staff`, quota journalier/hebdomadaire, unicité coupon/app/jour, unicité du code par app
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 8.1_
  - [ ]* 6.2 Écrire les tests de propriété pour `CouponV2View`
    - **Property 3 : Potential gain calculation** — `potential_gain == cote * 10000` pour toutes valeurs de `cote`
    - **Validates: Requirements 2.1**
    - **Property 4 : Combined coupon match count validation** — rejet si `coupon_type='combine'` et `match_count < 2`
    - **Validates: Requirements 2.2**
    - **Property 5 : One coupon per app per day** — rejet HTTP 429 si doublon auteur+app+jour
    - **Validates: Requirements 2.3**
    - **Property 6 : Daily and weekly quota enforcement** — rejet HTTP 429 si quota dépassé
    - **Validates: Requirements 2.4**
    - **Property 7 : Unique coupon code per app** — rejet si code dupliqué pour la même app
    - **Validates: Requirements 2.5**
    - **Property 20 : Permission enforcement on publish** — HTTP 403 si `can_publish_coupons=False` et non staff
    - **Validates: Requirements 8.1**
  - [x] 6.3 Implémenter `VoteCouponV2View` (APIView POST) avec :
    - Vérification `can_rate_coupons`
    - Interdiction du vote sur son propre coupon
    - Règle 1 vote/jour/auteur
    - Gestion des 3 cas : nouveau vote, annulation, changement
    - Mise à jour `likes_count`/`dislikes_count` et `coupon_points`
    - Ajustement `wallet.balance` si `enable_coupon_monetization`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 8.2_
  - [ ]* 6.4 Écrire les tests de propriété pour `VoteCouponV2View`
    - **Property 8 : One vote per day per author** — rejet HTTP 400 si déjà voté aujourd'hui pour cet auteur
    - **Validates: Requirements 3.1**
    - **Property 9 : No self-voting** — rejet HTTP 400 si l'auteur vote sur son propre coupon
    - **Validates: Requirements 3.2**
    - **Property 10 : Vote toggle (idempotence)** — double vote annule et restaure les compteurs
    - **Validates: Requirements 3.3**
    - **Property 11 : Vote change updates correctly** — changement de vote met à jour -1/+1 correctement
    - **Validates: Requirements 3.4**
    - **Property 12 : Wallet balance adjustment on vote** — balance change de ±monetization_amount
    - **Validates: Requirements 4.1, 4.2**
    - **Property 13 : Coupon points round-trip on vote** — vote + annulation laisse coupon_points inchangé
    - **Validates: Requirements 4.3, 4.4**
    - **Property 21 : Permission enforcement on vote** — HTTP 403 si `can_rate_coupons=False`
    - **Validates: Requirements 8.2**
  - [x] 6.5 Implémenter `CouponWalletView` (RetrieveAPIView) : retourne le solde et les statistiques du wallet de l'utilisateur connecté
    - _Requirements: 4.1, 4.2_
  - [x] 6.6 Implémenter `CouponWithdrawalView` (CreateAPIView) avec :
    - Validation `amount >= minimum_coupon_withdrawal`
    - Validation `amount <= wallet.balance`
    - Création `Transaction(type_trans="coupon_withdrawal")`
    - Débit `wallet.balance`, crédit `wallet.pending_payout`
    - Routage vers l'API de paiement via `connect_pro_withd_process()`
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ]* 6.7 Écrire les tests de propriété pour `CouponWithdrawalView`
    - **Property 14 : Withdrawal minimum validation** — rejet si `amount < minimum_coupon_withdrawal`
    - **Validates: Requirements 5.1**
    - **Property 15 : Withdrawal balance check** — rejet si `amount > wallet.balance`
    - **Validates: Requirements 5.2**
    - **Property 16 : Withdrawal fund conservation** — `balance + pending_payout` constant avant/après
    - **Validates: Requirements 5.3**
  - [x] 6.8 Implémenter `AuthorCommentView` (ListCreateAPIView + RetrieveUpdateDestroyAPIView) avec :
    - `POST` : créer un commentaire (JWT)
    - `GET ?coupon_author_id=<uuid>` : lister les commentaires top-level d'un auteur (parent=null)
    - `PATCH` : modifier (auteur uniquement)
    - `DELETE` : soft delete (`is_deleted=True`, `deleted_at=now()`)
    - _Requirements: 6.1, 6.2_
  - [ ]* 6.9 Écrire les tests de propriété pour `AuthorCommentView`
    - **Property 17 : Comment soft delete preserves record** — enregistrement toujours en DB avec `is_deleted=True`
    - **Validates: Requirements 6.1**
    - **Property 18 : Comment listing returns only top-level comments** — GET retourne uniquement `parent=null`
    - **Validates: Requirements 6.2**
  - [x] 6.10 Implémenter `AuthorRatingView` (CreateAPIView) : vote global sur un auteur (1 par auteur, `unique_together`)
    - _Requirements: 7.1_
  - [x] 6.11 Implémenter `UserCouponStatsView` (RetrieveAPIView) : statistiques de l'utilisateur connecté (coupons publiés, points, wallet)
    - _Requirements: 7.1_
  - [x] 6.12 Implémenter `AuthorStatsView` (RetrieveAPIView) : statistiques publiques d'un auteur avec calcul `author_rating = round((total_likes / (total_likes + total_dislikes)) * 5, 2)` (0.0 si aucun vote)
    - _Requirements: 7.2_
  - [ ]* 6.13 Écrire les tests de propriété pour `AuthorStatsView`
    - **Property 19 : Author rating formula** — formule correcte pour toutes combinaisons likes/dislikes, 0.0 si aucun vote
    - **Validates: Requirements 7.2**

- [ ] 7. Checkpoint — S'assurer que tous les tests passent, demander à l'utilisateur si des questions se posent.

- [x] 8. Ajouter les routes `/v2/` dans `mobcash_inte/urls.py`
  - Ajouter les patterns URL sous le préfixe `/v2/` :
    - `v2/coupons/` → `CouponV2View`
    - `v2/coupons/<uuid:pk>/vote/` → `VoteCouponV2View`
    - `v2/coupon-wallet/` → `CouponWalletView`
    - `v2/coupon-wallet-withdraw/` → `CouponWithdrawalView`
    - `v2/coupon-wallet-payouts/` → vue liste des payouts (Admin)
    - `v2/author-comments/` → `AuthorCommentView` (list/create)
    - `v2/author-comments/<uuid:pk>/` → `AuthorCommentView` (retrieve/update/delete)
    - `v2/author-ratings/` → `AuthorRatingView`
    - `v2/user/coupon-stats/` → `UserCouponStatsView`
    - `v2/author-stats/<uuid:user_id>/` → `AuthorStatsView`
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 7.2_

- [x] 9. Créer les tâches Celery dans `mobcash_inte/tasks.py`
  - [x] 9.1 Créer `grant_coupon_publishing_permissions` : attribue `can_publish_coupons=True` aux utilisateurs actifs avec `date_joined` ≥ 2 mois
    - _Requirements: 1.1_
  - [ ]* 9.2 Écrire les tests de propriété pour `grant_coupon_publishing_permissions`
    - **Property 1 : Permission grant threshold for publishing** — tout utilisateur éligible reçoit `can_publish_coupons=True`
    - **Validates: Requirements 1.1**
  - [x] 9.3 Créer `grant_coupon_rating_permissions` : attribue `can_rate_coupons=True` aux utilisateurs actifs avec `date_joined` ≥ 1 mois ET transactions acceptées ≥ 15 000 FCFA
    - Itérer les utilisateurs individuellement pour éviter les échecs en masse
    - _Requirements: 1.2_
  - [ ]* 9.4 Écrire les tests de propriété pour `grant_coupon_rating_permissions`
    - **Property 2 : Permission grant threshold for rating** — tout utilisateur éligible reçoit `can_rate_coupons=True`
    - **Validates: Requirements 1.2**
  - [x] 9.5 Enregistrer les deux tâches dans le beat schedule de Celery (quotidien à 00h00) dans `mobcash_inte_backend/celery.py`
    - _Requirements: 1.1, 1.2_

- [ ] 10. Enregistrer les nouveaux modèles dans `mobcash_inte/admin.py`
  - Enregistrer `CouponV2`, `CouponRatingV2`, `CouponWallet`, `CouponPayout`, `CouponWithdrawal`, `AuthorComment`, `AuthorCouponRating`
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.1, 7.1_

- [ ] 11. Checkpoint final — S'assurer que tous les tests passent, demander à l'utilisateur si des questions se posent.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriété utilisent `hypothesis` (`pip install hypothesis`)
- Chaque test de propriété doit tourner avec `@settings(max_examples=100)`
- Le modèle `Coupon` v1 existant ne doit pas être modifié — les nouveaux modèles sont préfixés `V2`
- Le signal `post_save` garantit qu'aucun utilisateur n'est sans wallet
