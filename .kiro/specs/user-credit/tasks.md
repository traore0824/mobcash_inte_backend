# Plan d'implémentation : UserCredit

## Vue d'ensemble

Ajout d'un mécanisme de crédit manuel attribué par un administrateur, automatiquement consommé lors du traitement d'un retrait dans `xbet_withdrawal_process()`. L'implémentation suit l'architecture Django REST Framework existante.

## Tâches

- [x] 1. Ajouter le modèle UserCredit et le champ credit_used sur Transaction
  - Dans `mobcash_inte/models.py`, ajouter la classe `UserCredit` avec les champs `id` (UUID), `user` (OneToOneField), `amount` (PositiveIntegerField, défaut 0), `note` (TextField nullable), `created_at`, `updated_at`
  - Dans `mobcash_inte/models.py`, ajouter le champ `credit_used = models.PositiveIntegerField(default=0)` sur le modèle `Transaction` existant
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [ ] 2. Créer et appliquer la migration Django
  - Générer la migration avec `python manage.py makemigrations`
  - Vérifier que la migration couvre bien le nouveau modèle `UserCredit` et le champ `credit_used` sur `Transaction`
  - _Requirements: 1.1, 2.1_

- [ ] 3. Ajouter UserCreditSerializer dans mobcash_inte/serializers.py
  - Créer `UserCreditSerializer` avec les champs `id`, `user` (lecture seule via SmallUserSerializer), `user_id` (écriture seule, PrimaryKeyRelatedField vers User), `amount`, `note`, `created_at`, `updated_at`
  - Ajouter la validation `amount >= 0` dans le sérialiseur
  - _Requirements: 3.2, 3.3, 6.2_

  - [ ]* 3.1 Écrire le test de propriété pour la validation du montant à l'API
    - **Property 7 : Validation du montant à l'API**
    - Générer des entiers négatifs via `hypothesis`, envoyer POST/PATCH, vérifier HTTP 400
    - **Validates: Requirements 6.2**

- [ ] 4. Ajouter UserCreditView et UserCreditDetailView dans mobcash_inte/views.py
  - Créer `UserCreditView(generics.ListCreateAPIView)` avec permission `IsAdminUser`
  - Surcharger `perform_create` pour implémenter le comportement `get_or_create` + remplacement du montant (non additif)
  - Retourner HTTP 404 si `user_id` inexistant
  - Créer `UserCreditDetailView(generics.RetrieveUpdateDestroyAPIView)` avec permission `IsAdminUser`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.1 Écrire les tests unitaires pour les vues admin
    - POST avec `user_id` valide → création et remplacement du montant
    - POST avec `user_id` inexistant → HTTP 404
    - POST par non-admin → HTTP 403
    - PATCH partiel sur un `UserCredit` existant
    - DELETE → suppression effective
    - _Requirements: 3.1, 3.4, 3.5, 4.2, 4.3_

  - [ ]* 4.2 Écrire le test de propriété pour l'idempotence du POST (remplacement)
    - **Property 6 : POST user-credit est idempotent sur le remplacement**
    - Générer deux montants distincts, POST successifs, vérifier que le second écrase le premier
    - **Validates: Requirements 3.2**

- [ ] 5. Créer mobcash_inte/admin_urls.py et l'inclure dans les URLs principales
  - Créer `mobcash_inte/admin_urls.py` avec les deux routes : `user-credit` et `user-credit/<uuid:pk>`
  - Dans `mobcash_inte_backend/urls.py`, inclure `admin_urls.py` sous le préfixe `betpay/`
  - _Requirements: 3.1, 3.6, 4.1, 4.2, 4.3_

- [ ] 6. Checkpoint — Vérifier que les endpoints admin fonctionnent
  - S'assurer que tous les tests passent, poser des questions à l'utilisateur si nécessaire.

- [ ] 7. Ajouter le hook de crédit dans xbet_withdrawal_process() dans payment.py
  - Importer `UserCredit` et `send_notification` en tête de fichier si nécessaire
  - Insérer le hook après la vérification `Success == true` et avant le retour `True`
  - Implémenter : récupération du crédit, calcul de `credit_to_apply = min(credit.amount, transaction.amount)`, déduction sur `transaction.amount` et `credit.amount`, enregistrement de `transaction.credit_used`
  - Sauvegarder `credit` et `transaction` selon les cas
  - Envoyer la notification avec titre "Crédit appliqué sur votre retrait" et contenu incluant le montant et la note du crédit comme raison
  - Court-circuiter avec `return False` si `transaction.amount <= 0` après déduction
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.3_

  - [ ]* 7.1 Écrire le test de propriété — le solde de crédit ne devient jamais négatif
    - **Property 1 : Le solde de crédit ne devient jamais négatif**
    - Générer des paires (credit_amount, tx_amount) aléatoires, appliquer le hook, vérifier `credit.amount >= 0`
    - **Validates: Requirements 6.1, 5.3**

  - [ ]* 7.2 Écrire le test de propriété — credit_to_apply est borné par le minimum
    - **Property 2 : credit_to_apply est borné par le minimum**
    - Générer des paires positives, vérifier `credit_to_apply == min(credit, tx)`
    - **Validates: Requirements 5.2**

  - [ ]* 7.3 Écrire le test de propriété — couverture totale évite l'appel externe
    - **Property 3 : Couverture totale du crédit évite l'appel externe**
    - Générer `tx_amount <= credit_amount`, vérifier `tx.amount == 0`, `status == "accept"`, retour `False`
    - **Validates: Requirements 5.4**

  - [ ]* 7.4 Écrire le test de propriété — couverture partielle poursuit le flux normal
    - **Property 4 : Couverture partielle du crédit poursuit le flux normal**
    - Générer `tx_amount > credit_amount > 0`, vérifier `tx.amount > 0`, retour `True`
    - **Validates: Requirements 5.5**

  - [ ]* 7.5 Écrire le test de propriété — absence de crédit ne modifie pas la transaction
    - **Property 5 : Absence de crédit ne modifie pas la transaction**
    - Générer des transactions sans UserCredit ou avec `amount=0`, vérifier invariance de `transaction.amount` et `transaction.credit_used`
    - **Validates: Requirements 5.6**

  - [ ]* 7.6 Écrire les tests unitaires pour le hook de crédit
    - Hook avec crédit = 0 → transaction inchangée
    - Hook avec crédit couvrant exactement le montant → `status = "accept"`, retour `False`
    - Hook avec `transaction.user = None` → pas d'erreur
    - _Requirements: 5.1, 5.4, 5.6_

- [ ] 8. Enregistrer UserCredit dans mobcash_inte/admin.py
  - Ajouter `admin.site.register(UserCredit)` dans `mobcash_inte/admin.py`
  - _Requirements: 1.1_

- [ ] 9. Checkpoint final — S'assurer que tous les tests passent
  - S'assurer que tous les tests passent, poser des questions à l'utilisateur si nécessaire.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriétés utilisent `hypothesis` avec `@settings(max_examples=100)`
- Les tests unitaires couvrent les cas limites et conditions d'erreur spécifiques
