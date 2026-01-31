# Documentation API CRUD - ID Link et User Phone

## Vue d'ensemble

Documentation des APIs CRUD pour gérer les IDs d'application (user-app-id) et les numéros de téléphone (user-phone) des utilisateurs.

**Base URL :** `/mobcash/`

---

## API 1 : CRUD User Phone (Numéros de Téléphone)

Gestion complète (Create, Read, Update, Delete) des numéros de téléphone associés aux réseaux pour un utilisateur.

### Endpoints

```
GET    /mobcash/user-phone/          # Lister les numéros
POST   /mobcash/user-phone/          # Créer un numéro
GET    /mobcash/user-phone/<id>/     # Détails d'un numéro
PUT    /mobcash/user-phone/<id>/     # Mettre à jour un numéro
PATCH  /mobcash/user-phone/<id>/     # Mettre à jour partiellement
DELETE /mobcash/user-phone/<id>/     # Supprimer un numéro
```

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Comportement selon le rôle

- **Utilisateur non-admin** : Voit et gère uniquement ses propres numéros
- **Administrateur** : Voit et gère tous les numéros

---

### GET : Lister les numéros de téléphone

#### Endpoint
```
GET /mobcash/user-phone/
```

#### Query Parameters (Optionnels)

**Filtres :**
| Paramètre | Type | Description |
|-----------|------|-------------|
| `user` | string (UUID) | Filtrer par ID utilisateur (admin uniquement) |
| `telegram_user` | string (UUID) | Filtrer par ID utilisateur Telegram (admin uniquement) |
| `network` | integer | Filtrer par ID de réseau |

**Recherche :**
| Paramètre | Type | Description |
|-----------|------|-------------|
| `search` | string | Recherche dans le champ `phone` |

#### Response Success (200 OK)

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "phone": "22912345678",
      "network": 1,
      "user": "550e8400-e29b-41d4-a716-446655440000",
      "telegram_user": null,
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": 2,
      "phone": "22987654321",
      "network": 2,
      "user": "550e8400-e29b-41d4-a716-446655440000",
      "telegram_user": null,
      "created_at": "2024-01-14T09:00:00Z"
    }
  ]
}
```

#### Champs retournés

| Champ | Type | Description |
|-------|------|-------------|
| `id` | integer | ID du numéro |
| `phone` | string | Numéro de téléphone |
| `network` | integer | ID du réseau (MTN, Moov, Orange, etc.) |
| `user` | string (UUID) | ID de l'utilisateur (null si Telegram) |
| `telegram_user` | string (UUID) | ID de l'utilisateur Telegram (null si User) |
| `created_at` | string (ISO 8601) | Date de création |

---

### POST : Créer un numéro de téléphone

#### Endpoint
```
POST /mobcash/user-phone/
```

#### Request Body

```json
{
  "phone": "22912345678",
  "network": 1
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `phone` | string | Oui | Numéro de téléphone |
| `network` | integer | Oui | ID du réseau |

**Note :** Les champs `user` et `telegram_user` sont automatiquement assignés selon l'utilisateur connecté.

#### Response Success (201 Created)

```json
{
  "id": 3,
  "phone": "22912345678",
  "network": 1,
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T11:00:00Z"
}
```

#### Response Errors

#### 400 Bad Request - Numéro déjà existant
```json
{
  "phone": ["Ce numéro existe déjà pour ce réseau et cet utilisateur."]
}
```

#### 400 Bad Request - Validation échouée
```json
{
  "phone": ["Ce champ est requis."],
  "network": ["Ce champ est requis."]
}
```

---

### GET : Détails d'un numéro

#### Endpoint
```
GET /mobcash/user-phone/<id>/
```

#### Path Parameters

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | integer | Oui | ID du numéro |

#### Response Success (200 OK)

```json
{
  "id": 1,
  "phone": "22912345678",
  "network": 1,
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T10:00:00Z"
}
```

#### Response Errors

#### 404 Not Found
```json
{
  "detail": "Not found."
}
```

---

### PUT/PATCH : Mettre à jour un numéro

#### Endpoint
```
PUT /mobcash/user-phone/<id>/
PATCH /mobcash/user-phone/<id>/
```

#### Request Body

```json
{
  "phone": "22912345679",
  "network": 2
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `phone` | string | Oui (PUT) / Optionnel (PATCH) | Nouveau numéro |
| `network` | integer | Oui (PUT) / Optionnel (PATCH) | Nouveau réseau |

#### Response Success (200 OK)

```json
{
  "id": 1,
  "phone": "22912345679",
  "network": 2,
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

### DELETE : Supprimer un numéro

#### Endpoint
```
DELETE /mobcash/user-phone/<id>/
```

#### Response Success (204 No Content)

Aucun contenu dans la réponse.

#### Response Errors

#### 404 Not Found
```json
{
  "detail": "Not found."
}
```

#### 403 Forbidden (si tentative de supprimer le numéro d'un autre utilisateur)
```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

## API 2 : CRUD User App ID (IDs d'Application)

Gestion complète (Create, Read, Update, Delete) des IDs d'application associés aux plateformes pour un utilisateur.

### Endpoints

```
GET    /mobcash/user-app-id/          # Lister les IDs
POST   /mobcash/user-app-id/          # Créer un ID
GET    /mobcash/user-app-id/<id>/     # Détails d'un ID
PUT    /mobcash/user-app-id/<id>/     # Mettre à jour un ID
PATCH  /mobcash/user-app-id/<id>/     # Mettre à jour partiellement
DELETE /mobcash/user-app-id/<id>/     # Supprimer un ID
```

### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

### Comportement selon le rôle

- **Utilisateur non-admin** : Voit et gère uniquement ses propres IDs
- **Administrateur** : Voit et gère tous les IDs

---

### GET : Lister les IDs d'application

#### Endpoint
```
GET /mobcash/user-app-id/
```

#### Query Parameters (Optionnels)

**Filtres :**
| Paramètre | Type | Description |
|-----------|------|-------------|
| `app_name` | string (UUID) | Filtrer par ID d'application |

**Recherche :**
| Paramètre | Type | Description |
|-----------|------|-------------|
| `search` | string | Recherche dans le champ `user_app_id` |

#### Response Success (200 OK)

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "user_app_id": "339966934",
      "app_name": "550e8400-e29b-41d4-a716-446655440000",
      "app_details": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "1xbet",
        "image": "https://example.com/1xbet.png",
        "enable": true
      },
      "user": "550e8400-e29b-41d4-a716-446655440000",
      "telegram_user": null,
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": 2,
      "user_app_id": "445577889",
      "app_name": "660e8400-e29b-41d4-a716-446655440001",
      "user": "550e8400-e29b-41d4-a716-446655440000",
      "telegram_user": null,
      "created_at": "2024-01-14T09:00:00Z"
    }
  ]
}
```

#### Champs retournés

| Champ | Type | Description |
|-------|------|-------------|
| `id` | integer | ID du lien |
| `user_app_id` | string | ID de l'utilisateur sur l'application |
| `app_name` | string (UUID) | ID de l'application (1xbet, Betway, etc.) |
| `app_details` | object | Détails de l'application (nom, image, enable) |
| `user` | string (UUID) | ID de l'utilisateur (null si Telegram) |
| `telegram_user` | string (UUID) | ID de l'utilisateur Telegram (null si User) |
| `created_at` | string (ISO 8601) | Date de création |

---

### POST : Créer un ID d'application

#### Endpoint
```
POST /mobcash/user-app-id/
```

#### Request Body

```json
{
  "user_app_id": "339966934",
  "app_name": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `user_app_id` | string | Oui | ID de l'utilisateur sur la plateforme |
| `app_name` | string (UUID) | Oui | ID de l'application |

**Note :** Les champs `user` et `telegram_user` sont automatiquement assignés selon l'utilisateur connecté.

#### Response Success (201 Created)

```json
{
  "id": 3,
  "user_app_id": "339966934",
  "app_name": "550e8400-e29b-41d4-a716-446655440000",
  "app_details": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "1xbet",
    "image": "https://example.com/1xbet.png",
    "enable": true
  },
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T11:00:00Z"
}
```

#### Response Errors

#### 400 Bad Request - Validation échouée
```json
{
  "user_app_id": ["Ce champ est requis."],
  "app_name": ["Ce champ est requis."]
}
```

---

### GET : Détails d'un ID

#### Endpoint
```
GET /mobcash/user-app-id/<id>/
```

#### Path Parameters

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | integer | Oui | ID du lien |

#### Response Success (200 OK)

```json
{
  "id": 1,
  "user_app_id": "339966934",
  "app_name": "550e8400-e29b-41d4-a716-446655440000",
  "app_details": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "1xbet",
    "image": "https://example.com/1xbet.png",
    "enable": true
  },
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

### PUT/PATCH : Mettre à jour un ID

#### Endpoint
```
PUT /mobcash/user-app-id/<id>/
PATCH /mobcash/user-app-id/<id>/
```

#### Request Body

```json
{
  "user_app_id": "445577889",
  "app_name": "660e8400-e29b-41d4-a716-446655440001"
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `user_app_id` | string | Oui (PUT) / Optionnel (PATCH) | Nouvel ID utilisateur |
| `app_name` | string (UUID) | Oui (PUT) / Optionnel (PATCH) | Nouvelle application |

#### Response Success (200 OK)

```json
{
  "id": 1,
  "user_app_id": "445577889",
  "app_name": "660e8400-e29b-41d4-a716-446655440001",
  "app_details": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Betway",
    "image": "https://example.com/betway.png",
    "enable": true
  },
  "user": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_user": null,
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

### DELETE : Supprimer un ID

#### Endpoint
```
DELETE /mobcash/user-app-id/<id>/
```

#### Response Success (204 No Content)

Aucun contenu dans la réponse.

#### Response Errors

#### 404 Not Found
```json
{
  "detail": "Not found."
}
```

#### 403 Forbidden (si tentative de supprimer l'ID d'un autre utilisateur)
```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

## Codes de Statut HTTP

| Code | Description |
|------|-------------|
| 200 | Succès (GET, PUT, PATCH) |
| 201 | Créé avec succès (POST) |
| 204 | Succès sans contenu (DELETE) |
| 400 | Requête invalide (validation échouée) |
| 401 | Non authentifié (token manquant ou invalide) |
| 403 | Permission refusée |
| 404 | Ressource non trouvée |

---

## Notes Importantes

### Sécurité

- Les utilisateurs non-admin ne peuvent voir et modifier que leurs propres ressources
- Les champs `user` et `telegram_user` sont automatiquement assignés et ne peuvent pas être modifiés
- Les administrateurs ont accès à toutes les ressources

### Validation

**User Phone :**
- Un utilisateur ne peut pas avoir le même numéro pour le même réseau (unicité)
- La validation vérifie l'unicité selon le type d'utilisateur (User ou TelegramUser)

**User App ID :**
- Un utilisateur peut avoir plusieurs IDs pour différentes applications
- Un utilisateur peut avoir plusieurs IDs pour la même application

### Pagination

Les deux APIs utilisent la pagination (CustomPagination) pour les listes.

### Filtres et Recherche

- **Filtres** : Utilisent DjangoFilterBackend
- **Recherche** : Utilisent SearchFilter (recherche partielle, insensible à la casse)

---

## Exemples de Cas d'Usage

### Cas 1 : Ajouter un numéro de téléphone MTN

```bash
POST /mobcash/user-phone/
Headers: Authorization: Bearer <access_token>
{
  "phone": "22912345678",
  "network": 1
}
```

### Cas 2 : Lister tous mes numéros

```bash
GET /mobcash/user-phone/
Headers: Authorization: Bearer <access_token>
```

### Cas 3 : Ajouter un ID pour 1xbet

```bash
POST /mobcash/user-app-id/
Headers: Authorization: Bearer <access_token>
{
  "user_app_id": "339966934",
  "app_name": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Cas 4 : Rechercher un ID par user_app_id

```bash
GET /mobcash/user-app-id/?search=339966934
Headers: Authorization: Bearer <access_token>
```

### Cas 5 : Mettre à jour un numéro

```bash
PATCH /mobcash/user-phone/1/
Headers: Authorization: Bearer <access_token>
{
  "phone": "22912345679"
}
```

### Cas 6 : Supprimer un ID

```bash
DELETE /mobcash/user-app-id/1/
Headers: Authorization: Bearer <access_token>
```

---

## Support

Pour toute question ou problème, contactez l'équipe de développement.

