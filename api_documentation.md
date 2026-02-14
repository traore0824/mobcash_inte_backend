# Documentation de l'API MobCash

Ce document regroupe la documentation technique des points d'entrée (endpoints) API demandés.

---

## 1. Notifications
Gère la récupération et l'envoi des notifications.

- **Endpoint :** `/notification`
- **Méthode GET :** Récupère la liste des notifications non lues de l'utilisateur authentifié.
- **Méthode POST :** (Admin) Permet d'envoyer une notification à un utilisateur spécifique ou à tous les administrateurs.
    - **Paramètres Query :** `user_id` (optionnel) pour cibler un utilisateur.
    - **Corps de la requête (JSON) :**
      ```json
      {
        "title": "Titre de la notification",
        "content": "Contenu du message"
      }
      ```

---

## 2. Réseaux (Networks)
Gère les réseaux de paiement disponibles.

- **Endpoint :** `/network`
- **Méthode GET :** Récupère la liste des réseaux configurés.
    - **Paramètres Query :** `type` (valeurs possibles : `deposit` ou `withdrawal`) pour filtrer les réseaux actifs pour les dépôts ou les retraits.
- **Méthode POST :** (Admin uniquement) Permet de créer un nouveau réseau.

---

## 3. Plateformes (Platforms / AppName)
Gère les applications de paris supportées (ex: 1xbet, betwinner).

- **Endpoint :** `/plateform`
- **Méthode GET :** Récupère la liste des plateformes actives.
    - **Paramètres Query :** `type` (valeurs possibles : `deposit` ou `withdrawal`) pour filtrer les plateformes.
- **Méthode POST :** (Admin uniquement) Permet d'ajouter une nouvelle plateforme.

---

## 4. Création de Transaction de Dépôt
Initie une transaction de dépôt d'argent.

- **Endpoint :** `/transaction-deposit`
- **Méthode :** POST
- **Corps de la requête (JSON) :**
  ```json
  {
    "amount": 1000,
    "phone_number": "0102030405",
    "app": 1, 
    "user_app_id": "ID_JOUEUR",
    "network": 1,
    "source": "mobile"
  }
  ```
- **Description :** Crée une transaction de dépôt, génère une référence unique et lance le processus de paiement via le réseau sélectionné.

---

## 5. Transaction de Retrait
Gère les demandes de retrait d'argent.

- **Endpoint :** `/transaction-withdrawal`
- **Méthode :** POST
- **Corps de la requête (JSON) :**
  ```json
  {
    "amount": 5000,
    "phone_number": "0102030405",
    "app": 1,
    "user_app_id": "ID_JOUEUR",
    "network": 1,
    "withdriwal_code": "CODE_RETRAIT",
    "source": "mobile"
  }
  ```
- **Description :** Enregistre une demande de retrait avec le code fourni par la plateforme de paris.

---

## 6. Transaction de Dépôt via Bonus (Reward)
Permet de recharger son compte de paris en utilisant ses bonus accumulés.

- **Endpoint :** `/transaction-bonus`
- **Méthode :** POST
- **Corps de la requête (JSON) :**
  ```json
  {
    "app": 1,
    "user_app_id": "ID_JOUEUR",
    "amount": 1000,
    "source": "mobile"
  }
  ```
- **Description :** Utilise le solde de bonus de l'utilisateur pour effectuer un dépôt sur la plateforme de paris spécifiée.

---

## 7. Publicités (Advertisements)
Gère les bannières publicitaires affichées dans l'application.

- **Endpoint :** `/ann`
- **Méthode GET :** Récupère la liste des publicités actives (activées via le champ `enable`).
- **Méthode POST :** (Admin uniquement) Permet de créer une nouvelle publicité en téléchargeant une image.
    - **Type de contenu :** `multipart/form-data`
    - **Champs :** `image` (Fichier), `enable` (Boolean).

---

## 8. Gestion des Numéros de Téléphone (UserPhone)
Permet de gérer les numéros de téléphone de l'utilisateur pour les différents réseaux.

- **Endpoint :** `/user-phone/`
- **Méthode GET (List) :** Récupère tous les numéros de téléphone de l'utilisateur.
- **Méthode POST (Create) :** Ajoute un nouveau numéro de téléphone.
    - **Corps (JSON) :**
      ```json
      {
        "phone": "0102030405",
        "network": 1
      }
      ```
- **Méthode GET (Retrieve) :** `/user-phone/<id>/` récupère les détails d'un numéro.
- **Méthode PUT/PATCH (Update) :** `/user-phone/<id>/` modifie un numéro.
- **Méthode DELETE (Delete) :** `/user-phone/<id>/` supprime un numéro.

---

## 9. Gestion des IDs de Joueurs (IDLink)
Permet de lier et gérer les IDs de joueurs pour les différentes plateformes de paris.

- **Endpoint :** `/user-app-id/`
- **Méthode GET (List) :** Récupère tous les IDs de joueurs liés à l'utilisateur.
- **Méthode POST (Create) :** Lie un nouvel ID de joueur à une plateforme.
    - **Corps (JSON) :**
      ```json
      {
        "user_app_id": "ID_JOUEUR",
        "app_name": 1
      }
      ```
- **Méthode GET (Retrieve) :** `/user-app-id/<id>/` récupère les détails d'un lien.
- **Méthode PUT/PATCH (Update) :** `/user-app-id/<id>/` modifie un lien.
- **Méthode DELETE (Delete) :** `/user-app-id/<id>/` supprime un lien.

