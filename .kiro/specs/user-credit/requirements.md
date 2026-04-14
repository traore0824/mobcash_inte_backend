# Requirements Document

## Introduction

La fonctionnalité **UserCredit** permet à un administrateur d'attribuer manuellement un crédit en FCFA à un utilisateur. Ce crédit est automatiquement déduit du montant d'un retrait au moment de son traitement, réduisant ainsi le montant réel que la plateforme doit envoyer à l'utilisateur via l'API de paiement. Si le crédit couvre intégralement le montant du retrait, aucun appel à l'API de paiement externe n'est effectué.

## Glossary

- **UserCredit**: Enregistrement unique par utilisateur représentant un solde de crédit en FCFA attribué manuellement par un administrateur.
- **Credit_System**: Le sous-système Django responsable de la gestion des crédits utilisateurs (modèle, vues, sérialiseurs).
- **Admin**: Utilisateur Django avec le flag `is_staff=True` ou `is_superuser=True`.
- **Transaction**: Enregistrement d'une opération financière (dépôt ou retrait) dans `mobcash_inte/models.py`.
- **Withdrawal_Processor**: La fonction `xbet_withdrawal_process()` dans `payment.py`, responsable du traitement des retraits.
- **credit_used**: Champ `PositiveIntegerField` sur le modèle `Transaction` traçant le montant de crédit consommé lors d'un retrait.
- **FCFA**: Franc CFA, unité monétaire utilisée dans le système.

---

## Requirements

### Requirement 1: Modèle UserCredit

**User Story:** En tant qu'administrateur, je veux qu'un enregistrement de crédit unique soit associé à chaque utilisateur, afin de pouvoir gérer le solde de crédit de manière fiable.

#### Acceptance Criteria

1. THE Credit_System SHALL stocker le crédit d'un utilisateur dans un modèle `UserCredit` avec les champs : `id` (UUID, clé primaire), `user` (OneToOneField vers User), `amount` (PositiveIntegerField, défaut 0), `note` (TextField, optionnel), `created_at` et `updated_at`.
2. THE Credit_System SHALL garantir qu'un seul enregistrement `UserCredit` existe par utilisateur via la contrainte `OneToOneField`.
3. WHEN un enregistrement `UserCredit` est supprimé, THE Credit_System SHALL supprimer en cascade l'enregistrement lié à l'utilisateur (`on_delete=CASCADE`).

---

### Requirement 2: Champ credit_used sur Transaction

**User Story:** En tant qu'administrateur, je veux pouvoir tracer combien de crédit a été consommé sur chaque transaction de retrait, afin d'avoir un historique complet des déductions.

#### Acceptance Criteria

1. THE Credit_System SHALL ajouter un champ `credit_used` de type `PositiveIntegerField` (défaut 0, nullable) sur le modèle `Transaction`.
2. WHEN aucun crédit n'est appliqué à une transaction, THE Credit_System SHALL conserver `credit_used` à 0.

---

### Requirement 3: API Admin — Création et mise à jour du crédit

**User Story:** En tant qu'administrateur, je veux créer ou écraser le crédit d'un utilisateur via une API REST, afin de pouvoir ajuster manuellement le solde de crédit.

#### Acceptance Criteria

1. THE Credit_System SHALL exposer un endpoint `POST /betpay/user-credit` accessible uniquement aux utilisateurs avec permission `IsAdminUser`.
2. WHEN un administrateur envoie une requête `POST /betpay/user-credit` avec un `user_id` et un `amount` valides, THE Credit_System SHALL créer ou récupérer l'enregistrement `UserCredit` de cet utilisateur via `get_or_create`, puis remplacer le champ `amount` par la valeur fournie (comportement de remplacement, non additif).
3. WHEN un administrateur envoie une requête `POST /betpay/user-credit` avec un champ `note`, THE Credit_System SHALL enregistrer la note sur l'enregistrement `UserCredit`.
4. IF un utilisateur avec l'`user_id` fourni n'existe pas, THEN THE Credit_System SHALL retourner une réponse HTTP 404.
5. IF la requête `POST /betpay/user-credit` est envoyée par un utilisateur non administrateur, THEN THE Credit_System SHALL retourner une réponse HTTP 403.
6. THE Credit_System SHALL exposer un endpoint `GET /betpay/user-credit` accessible uniquement aux utilisateurs avec permission `IsAdminUser`, retournant la liste paginée de tous les enregistrements `UserCredit`.

---

### Requirement 4: API Admin — Détail, modification et suppression du crédit

**User Story:** En tant qu'administrateur, je veux consulter, modifier ou supprimer un enregistrement de crédit spécifique via son identifiant, afin de gérer finement les crédits attribués.

#### Acceptance Criteria

1. THE Credit_System SHALL exposer un endpoint `GET /betpay/user-credit/<id>` accessible uniquement aux utilisateurs avec permission `IsAdminUser`, retournant les détails d'un enregistrement `UserCredit`.
2. THE Credit_System SHALL exposer un endpoint `PATCH /betpay/user-credit/<id>` accessible uniquement aux utilisateurs avec permission `IsAdminUser`, permettant la mise à jour partielle d'un enregistrement `UserCredit`.
3. THE Credit_System SHALL exposer un endpoint `DELETE /betpay/user-credit/<id>` accessible uniquement aux utilisateurs avec permission `IsAdminUser`, supprimant l'enregistrement `UserCredit`.
4. IF un enregistrement `UserCredit` avec l'`id` fourni n'existe pas, THEN THE Credit_System SHALL retourner une réponse HTTP 404.
5. IF une requête sur `/betpay/user-credit/<id>` est envoyée par un utilisateur non administrateur, THEN THE Credit_System SHALL retourner une réponse HTTP 403.

---

### Requirement 5: Application automatique du crédit lors d'un retrait

**User Story:** En tant qu'utilisateur, je veux que mon crédit soit automatiquement déduit du montant de mon retrait lors du traitement, afin de bénéficier du crédit qui m'a été accordé sans action supplémentaire de ma part.

#### Acceptance Criteria

1. WHEN la fonction `xbet_withdrawal_process()` traite un retrait avec succès (réponse `Success=true` de l'API MobCash), THE Withdrawal_Processor SHALL vérifier si l'utilisateur associé à la transaction possède un enregistrement `UserCredit` avec un `amount` supérieur à 0.
2. WHEN un crédit est disponible pour l'utilisateur, THE Withdrawal_Processor SHALL calculer `credit_to_apply = min(credit.amount, transaction.amount)`.
3. WHEN `credit_to_apply` est calculé, THE Withdrawal_Processor SHALL déduire `credit_to_apply` du `transaction.amount`, enregistrer `credit_to_apply` dans `transaction.credit_used`, et déduire `credit_to_apply` du `credit.amount`.
4. WHEN le `transaction.amount` devient inférieur ou égal à 0 après déduction du crédit, THE Withdrawal_Processor SHALL définir `transaction.amount = 0`, `transaction.status = "accept"`, sauvegarder la transaction, et retourner `False` pour indiquer qu'aucun appel à l'API de paiement externe n'est nécessaire.
5. WHEN le `transaction.amount` reste supérieur à 0 après déduction du crédit, THE Withdrawal_Processor SHALL poursuivre le flux normal de paiement (appel à l'API de paiement externe).
6. WHEN aucun enregistrement `UserCredit` n'existe pour l'utilisateur ou que `credit.amount` est égal à 0, THE Withdrawal_Processor SHALL poursuivre le flux normal de paiement sans modification du montant.
7. THE Withdrawal_Processor SHALL sauvegarder l'enregistrement `UserCredit` mis à jour (solde réduit) après chaque application de crédit.

---

### Requirement 6: Intégrité et cohérence des données

**User Story:** En tant qu'administrateur, je veux que les opérations de crédit soient atomiques et cohérentes, afin d'éviter toute incohérence de données en cas d'erreur concurrente.

#### Acceptance Criteria

1. WHEN le crédit est appliqué à une transaction, THE Withdrawal_Processor SHALL garantir que `credit.amount` ne devient jamais négatif (valeur minimale : 0).
2. THE Credit_System SHALL valider que le champ `amount` d'un `UserCredit` est un entier positif ou nul lors de la création et de la mise à jour via l'API.
3. IF une erreur survient lors de la sauvegarde du crédit ou de la transaction pendant l'application du crédit, THEN THE Withdrawal_Processor SHALL propager l'exception pour permettre un rollback de la transaction Django.
