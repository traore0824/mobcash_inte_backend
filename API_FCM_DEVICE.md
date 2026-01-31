# Documentation API - Gestion des Devices FCM (Firebase Cloud Messaging)

## Vue d'ensemble

API pour gérer les tokens FCM (Firebase Cloud Messaging) des appareils des utilisateurs. Permet d'enregistrer, lister, mettre à jour et supprimer les devices pour l'envoi de notifications push.

**Base URL :** `/mobcash/devices/`

**Bibliothèque utilisée :** `fcm-django` (FCMDeviceAuthorizedViewSet)

---

## Configuration

Les paramètres FCM sont configurés dans `settings.py` :

```python
FCM_DJANGO_SETTINGS = {
    "ONE_DEVICE_PER_USER": False,  # Permet plusieurs devices par utilisateur
    "DELETE_INACTIVE_DEVICES": False,  # Ne supprime pas automatiquement les devices inactifs
}
```

---

## Endpoints Disponibles

### 1. Enregistrer un Device FCM

Enregistre un nouveau token FCM pour l'utilisateur authentifié.

#### Endpoint

```
POST /mobcash/devices/
```

#### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

#### Request Body

```json
{
  "registration_id": "fcm_token_here",
  "type": "android",
  "name": "Mon Appareil"
}
```

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `registration_id` | string | Oui | Token FCM de l'appareil (obtenu depuis Firebase) |
| `type` | string | Non | Type d'appareil : `android`, `ios`, `web` (défaut: `android`) |
| `name` | string | Non | Nom de l'appareil (pour identification) |

#### Response Success (201 Created)

```json
{
  "id": 1,
  "name": "Mon Appareil",
  "active": true,
  "user": 123,
  "date_created": "2024-01-15T10:00:00Z",
  "type": "android",
  "registration_id": "fcm_token_here"
}
```

#### Response Errors

##### 400 Bad Request - Token déjà enregistré

```json
{
  "registration_id": ["device with this registration id already exists."]
}
```

##### 401 Unauthorized

```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

---

### 2. Lister les Devices de l'Utilisateur

Récupère la liste de tous les devices FCM enregistrés pour l'utilisateur authentifié.

#### Endpoint

```
GET /mobcash/devices/
```

#### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

#### Query Parameters

| Paramètre | Type | Description |
|-----------|------|-------------|
| `active` | boolean | Filtrer par statut actif/inactif |
| `type` | string | Filtrer par type d'appareil (`android`, `ios`, `web`) |

#### Response Success (200 OK)

```json
[
  {
    "id": 1,
    "name": "Mon Appareil Android",
    "active": true,
    "user": 123,
    "date_created": "2024-01-15T10:00:00Z",
    "type": "android",
    "registration_id": "fcm_token_1"
  },
  {
    "id": 2,
    "name": "Mon iPhone",
    "active": true,
    "user": 123,
    "date_created": "2024-01-16T14:30:00Z",
    "type": "ios",
    "registration_id": "fcm_token_2"
  }
]
```

#### Response Errors

##### 401 Unauthorized

```json
{
  "detail": "Les identifiants d'authentification n'ont pas été fournis."
}
```

---

### 3. Récupérer les Détails d'un Device

Récupère les détails d'un device spécifique.

#### Endpoint

```
GET /mobcash/devices/{id}/
```

#### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

#### Paramètres d'URL

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | integer | ID du device |

#### Response Success (200 OK)

```json
{
  "id": 1,
  "name": "Mon Appareil Android",
  "active": true,
  "user": 123,
  "date_created": "2024-01-15T10:00:00Z",
  "type": "android",
  "registration_id": "fcm_token_here"
}
```

#### Response Errors

##### 404 Not Found

```json
{
  "detail": "Not found."
}
```

##### 403 Forbidden - Device appartient à un autre utilisateur

```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

### 4. Mettre à Jour un Device

Met à jour les informations d'un device (nom, type, statut actif).

#### Endpoint

```
PUT /mobcash/devices/{id}/
PATCH /mobcash/devices/{id}/
```

#### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

#### Paramètres d'URL

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | integer | ID du device |

#### Request Body (PUT - tous les champs requis)

```json
{
  "registration_id": "fcm_token_here",
  "type": "android",
  "name": "Nouveau Nom",
  "active": true
}
```

#### Request Body (PATCH - champs optionnels)

```json
{
  "name": "Nouveau Nom",
  "active": false
}
```

#### Response Success (200 OK)

```json
{
  "id": 1,
  "name": "Nouveau Nom",
  "active": false,
  "user": 123,
  "date_created": "2024-01-15T10:00:00Z",
  "type": "android",
  "registration_id": "fcm_token_here"
}
```

#### Response Errors

##### 400 Bad Request - Validation échouée

```json
{
  "registration_id": ["Ce champ est requis."]
}
```

##### 404 Not Found

```json
{
  "detail": "Not found."
}
```

##### 403 Forbidden

```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

### 5. Supprimer un Device

Supprime un device FCM.

#### Endpoint

```
DELETE /mobcash/devices/{id}/
```

#### Authentification

**Requis :** Token d'authentification dans les headers
```
Authorization: Bearer <access_token>
```

#### Paramètres d'URL

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | integer | ID du device |

#### Response Success (204 No Content)

Aucun contenu retourné (statut 204).

#### Response Errors

##### 404 Not Found

```json
{
  "detail": "Not found."
}
```

##### 403 Forbidden

```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

## Structure des Données

### Device Object

| Champ | Type | Description |
|-------|------|-------------|
| `id` | integer | ID unique du device |
| `name` | string | Nom de l'appareil (optionnel) |
| `active` | boolean | Statut actif/inactif du device |
| `user` | integer | ID de l'utilisateur propriétaire |
| `date_created` | datetime | Date de création du device |
| `type` | string | Type d'appareil : `android`, `ios`, `web` |
| `registration_id` | string | Token FCM unique de l'appareil |

---

## Comportement et Règles

### Multiples Devices par Utilisateur

- **Configuration actuelle** : `ONE_DEVICE_PER_USER = False`
- Un utilisateur peut avoir plusieurs devices enregistrés
- Utile pour les utilisateurs ayant plusieurs appareils (téléphone, tablette, etc.)

### Gestion des Tokens

- Chaque `registration_id` (token FCM) doit être unique dans le système
- Si un token est déjà enregistré, une erreur 400 est retournée
- Les tokens peuvent être mis à jour via PUT/PATCH

### Sécurité

- Les utilisateurs ne peuvent voir et modifier que leurs propres devices
- Un utilisateur ne peut pas accéder aux devices d'un autre utilisateur (403 Forbidden)
- L'authentification est requise pour toutes les opérations

### Devices Inactifs

- **Configuration actuelle** : `DELETE_INACTIVE_DEVICES = False`
- Les devices inactifs ne sont pas supprimés automatiquement
- Vous pouvez désactiver un device en mettant `active: false` via PATCH

---

## Exemples d'Utilisation

### Exemple 1 : Enregistrer un nouveau device Android

```bash
curl -X POST https://api.example.com/mobcash/devices/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "registration_id": "fcm_token_from_firebase",
    "type": "android",
    "name": "Mon Téléphone"
  }'
```

### Exemple 2 : Lister tous mes devices

```bash
curl -X GET https://api.example.com/mobcash/devices/ \
  -H "Authorization: Bearer <access_token>"
```

### Exemple 3 : Mettre à jour le nom d'un device

```bash
curl -X PATCH https://api.example.com/mobcash/devices/1/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Nouveau Nom d Appareil"
  }'
```

### Exemple 4 : Désactiver un device

```bash
curl -X PATCH https://api.example.com/mobcash/devices/1/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "active": false
  }'
```

### Exemple 5 : Supprimer un device

```bash
curl -X DELETE https://api.example.com/mobcash/devices/1/ \
  -H "Authorization: Bearer <access_token>"
```

---

## Intégration dans l'Application Mobile

### Flux Recommandé

1. **Au démarrage de l'app** :
   - Obtenir le token FCM depuis Firebase
   - Enregistrer le device via `POST /mobcash/devices/`

2. **Lors de la mise à jour du token** :
   - Si le token FCM change (rare mais possible)
   - Mettre à jour via `PATCH /mobcash/devices/{id}/` avec le nouveau `registration_id`

3. **Lors de la déconnexion** :
   - Optionnel : Désactiver le device (`active: false`) ou le supprimer

### Exemple de Code (Flutter/Dart)

```dart
// 1. Obtenir le token FCM
String? fcmToken = await FirebaseMessaging.instance.getToken();

// 2. Enregistrer le device
if (fcmToken != null) {
  final response = await http.post(
    Uri.parse('https://api.example.com/mobcash/devices/'),
    headers: {
      'Authorization': 'Bearer $accessToken',
      'Content-Type': 'application/json',
    },
    body: jsonEncode({
      'registration_id': fcmToken,
      'type': 'android', // ou 'ios'
      'name': 'Mon Appareil',
    }),
  );
  
  if (response.statusCode == 201) {
    print('Device enregistré avec succès');
  }
}
```

### Exemple de Code (React Native)

```javascript
import messaging from '@react-native-firebase/messaging';

// 1. Obtenir le token FCM
const fcmToken = await messaging().getToken();

// 2. Enregistrer le device
if (fcmToken) {
  const response = await fetch('https://api.example.com/mobcash/devices/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      registration_id: fcmToken,
      type: Platform.OS === 'ios' ? 'ios' : 'android',
      name: 'Mon Appareil',
    }),
  });
  
  if (response.ok) {
    console.log('Device enregistré avec succès');
  }
}
```

---

## Utilisation pour l'Envoi de Notifications

Les devices enregistrés sont utilisés automatiquement par le système pour envoyer des notifications push. La fonction `send_push_noti` dans `mobcash_inte/helpers.py` utilise les devices FCM :

```python
def send_push_noti(user: User, title, body, data=None):
    devices = FCMDevice.objects.filter(user=user)[:3]
    for device in devices:
        response = call_api(
            device.registration_id, title=title, body=body, message_data=data
        )
        return response
```

**Note :** Seuls les 3 premiers devices actifs de l'utilisateur sont utilisés pour l'envoi de notifications.

---

## Codes de Statut HTTP

| Code | Description |
|------|-------------|
| 200 | Succès (GET, PUT, PATCH) |
| 201 | Créé avec succès (POST) |
| 204 | Supprimé avec succès (DELETE) |
| 400 | Requête invalide (validation échouée) |
| 401 | Non authentifié (token manquant ou invalide) |
| 403 | Permission refusée (device d'un autre utilisateur) |
| 404 | Device non trouvé |
| 500 | Erreur serveur |

---

## Notes Importantes

### Gestion des Tokens FCM

- Les tokens FCM peuvent changer dans certains cas (réinstallation de l'app, etc.)
- Il est recommandé de vérifier périodiquement si le token est toujours valide
- En cas de token invalide, mettre à jour le device avec le nouveau token

### Performance

- Un utilisateur peut avoir plusieurs devices (pas de limite configurée)
- Pour l'envoi de notifications, seuls les 3 premiers devices actifs sont utilisés
- Les devices inactifs ne sont pas supprimés automatiquement

### Sécurité

- Les tokens FCM sont sensibles et ne doivent pas être exposés publiquement
- L'authentification est obligatoire pour toutes les opérations
- Les utilisateurs ne peuvent accéder qu'à leurs propres devices

---

## Support

Pour toute question ou problème concernant cette API, contactez l'équipe de développement.

