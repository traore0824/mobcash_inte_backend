# Documentation - Processus de Réinitialisation de Mot de Passe

## Vue d'ensemble

Le processus de réinitialisation de mot de passe se déroule en 3 étapes :
1. **Envoi de l'OTP** - L'utilisateur demande un code de vérification
2. **Validation de l'OTP** (optionnel) - Vérification que le code est valide
3. **Réinitialisation du mot de passe** - Changement du mot de passe avec le code OTP

---

## Étape 1 : Envoi de l'OTP

### Endpoint
```
POST /auth/send_otp
```

### Description
Génère et envoie un code OTP (One-Time Password) par email à l'utilisateur pour réinitialiser son mot de passe. Le code est valide pendant 2 minutes.

### Request Body
```json
{
  "email": "user@example.com"
}
```

#### Paramètres
| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| email | string | Oui | Adresse email de l'utilisateur |

### Responses

#### Succès - 200 OK
```json
{}
```
**Note importante** : L'endpoint retourne toujours 200 OK, même si l'email n'existe pas dans la base de données. Ceci est une mesure de sécurité pour éviter l'énumération des comptes.

### Comportement
- Si l'utilisateur existe, un OTP est généré et envoyé par email
- L'OTP expire après 2 minutes
- Si l'utilisateur n'existe pas, aucune erreur n'est retournée (sécurité)

---

## Étape 2 : Validation de l'OTP (Optionnel)

### Endpoint
```
POST /auth/validate_otp
```

### Description
Vérifie que le code OTP fourni est valide et n'a pas expiré. Cette étape est optionnelle mais recommandée pour valider le code avant de réinitialiser le mot de passe.

### Request Body
```json
{
  "otp": "123456"
}
```

#### Paramètres
| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| otp | string | Oui | Code OTP reçu par email (minimum 4 caractères) |

### Responses

#### Succès - 200 OK
```json
{}
```
L'OTP est valide et marqué comme vérifié dans le système.

#### Erreur - 404 Not Found
```json
{
  "success": false,
  "details": "The verification code is incorrect or has expired. Please request a new code."
}
```

### Comportement
- Vérifie que l'OTP existe et n'a pas expiré
- Marque l'OTP comme validé (`otp_is_valid = True`)
- Retourne une erreur si l'OTP est invalide ou expiré

---

## Étape 3 : Réinitialisation du Mot de Passe

### Endpoint
```
POST /auth/reset_password
```

### Description
Réinitialise le mot de passe de l'utilisateur en utilisant le code OTP reçu par email.

### Request Body
```json
{
  "otp": "123456",
  "new_password": "NewSecurePassword123",
  "confirm_new_password": "NewSecurePassword123"
}
```

#### Paramètres
| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| otp | string | Oui | Code OTP reçu par email (minimum 4 caractères) |
| new_password | string | Oui | Nouveau mot de passe (minimum 6 caractères) |
| confirm_new_password | string | Oui | Confirmation du nouveau mot de passe (minimum 6 caractères) |

### Validation
- Les deux mots de passe doivent correspondre
- Le mot de passe doit contenir au moins 6 caractères
- L'OTP doit exister dans la base de données

### Responses

#### Succès - 200 OK
```json
{}
```
Le mot de passe a été réinitialisé avec succès. L'OTP est supprimé de la base de données.

#### Erreur - 400 Bad Request
```json
{
  "password": "The passwords do not match."
}
```
Les mots de passe ne correspondent pas.

#### Erreur - 404 Not Found
```json
{
  "success": false,
  "details": "User not found !"
}
```
Aucun utilisateur trouvé avec cet OTP (OTP invalide ou expiré).

### Comportement
- Vérifie que l'OTP existe (pas de vérification d'expiration à cette étape)
- Change le mot de passe de l'utilisateur
- Supprime l'OTP de la base de données (`otp = None`)
- Hash automatiquement le nouveau mot de passe

---

## Flux Complet - Exemple

### Scénario : Utilisateur oublie son mot de passe

#### 1. Demande d'OTP
```bash
curl -X POST http://api.example.com/auth/send_otp \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

**Réponse :** `200 OK`

L'utilisateur reçoit un email avec le code OTP (ex: 123456)

#### 2. Validation de l'OTP (optionnel)
```bash
curl -X POST http://api.example.com/auth/validate_otp \
  -H "Content-Type: application/json" \
  -d '{"otp": "123456"}'
```

**Réponse :** `200 OK`

#### 3. Réinitialisation du mot de passe
```bash
curl -X POST http://api.example.com/auth/reset_password \
  -H "Content-Type: application/json" \
  -d '{
    "otp": "123456",
    "new_password": "NewSecurePassword123",
    "confirm_new_password": "NewSecurePassword123"
  }'
```

**Réponse :** `200 OK`

Le mot de passe est maintenant changé. L'utilisateur peut se connecter avec son nouveau mot de passe.

---

## Sécurité

### Mesures de sécurité implémentées :
- **Expiration de l'OTP** : Le code expire après 2 minutes
- **Protection contre l'énumération** : L'endpoint `send_otp` retourne toujours 200 OK
- **Hash du mot de passe** : Les mots de passe sont automatiquement hashés
- **Validation des mots de passe** : Vérification de la correspondance et de la longueur minimale
- **Suppression de l'OTP** : L'OTP est supprimé après utilisation

### Recommandations :
- Limiter le nombre de tentatives d'envoi d'OTP par IP/email
- Ajouter une vérification d'expiration dans l'endpoint `reset_password`
- Implémenter un rate limiting sur tous les endpoints
- Envisager d'ajouter un CAPTCHA pour l'envoi d'OTP

---

## Codes d'Erreur

| Code | Description |
|------|-------------|
| 200 | Succès |
| 400 | Erreur de validation (mots de passe ne correspondent pas) |
| 404 | Ressource non trouvée (OTP invalide ou utilisateur inexistant) |

---

## Notes Techniques

### Modèle User
Les champs utilisés pour le reset password :
- `otp` : Code de vérification (string, nullable)
- `otp_created_at` : Date d'expiration de l'OTP (datetime)
- `otp_is_valid` : Indicateur de validation (boolean)
- `email` : Email de l'utilisateur

### Template Email
Le template utilisé pour l'email : `templates/reset_password.html`

### Durée de validité
L'OTP est valide pendant **2 minutes** après sa création.
