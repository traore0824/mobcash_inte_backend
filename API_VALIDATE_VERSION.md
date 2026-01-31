# Documentation API - Validation de Version APK

## Vue d'ensemble

API pour valider la version de l'application mobile de l'utilisateur et déterminer si une mise à jour est nécessaire (obligatoire ou optionnelle).

**Base URL :** `/mobcash/`

---

## Endpoint

```
POST /mobcash/validate-version
```

## Description

Valide la version de l'application de l'utilisateur en la comparant avec les paramètres de version configurés dans le Setting (`min_version` et `last_version`). Retourne des informations sur la nécessité d'une mise à jour et le lien de téléchargement de l'APK.

### Authentification

**Non requise** : Cette API est accessible publiquement (`AllowAny`)

### Request Body

```json
{
  "version": 5
}
```

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `version` | integer | Oui | Version actuelle de l'application de l'utilisateur (nombre positif) |

### Validations

- La version doit être un nombre entier positif (≥ 1)
- Si la version est ≤ 0, une erreur de validation est retournée

---

## Response Success (200 OK)

### Cas 1 : Version à jour (pas de mise à jour nécessaire)

```json
{
  "valid": true,
  "update_required": false,
  "update_available": false,
  "current_version": 10,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

**Condition :** `current_version >= last_version`

### Cas 2 : Mise à jour optionnelle disponible

```json
{
  "valid": true,
  "update_required": false,
  "update_available": true,
  "current_version": 8,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

**Condition :** `min_version <= current_version < last_version`

### Cas 3 : Mise à jour obligatoire

```json
{
  "valid": false,
  "update_required": true,
  "update_available": true,
  "current_version": 3,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

**Condition :** `current_version < min_version`

### Cas 4 : Versions non configurées

```json
{
  "valid": true,
  "update_required": false,
  "update_available": false,
  "current_version": 5,
  "min_version": null,
  "last_version": null,
  "download_link": "https://example.com/app.apk"
}
```

**Condition :** `min_version` et `last_version` sont `null` dans le Setting

---

## Champs de la Réponse

| Champ | Type | Description |
|-------|------|-------------|
| `valid` | boolean | Indique si la version actuelle est valide (≥ min_version) |
| `update_required` | boolean | `true` si la mise à jour est obligatoire (version < min_version) |
| `update_available` | boolean | `true` si une mise à jour est disponible (version < last_version) |
| `current_version` | integer | Version actuelle de l'utilisateur (celle envoyée dans la requête) |
| `min_version` | integer \| null | Version minimum requise configurée dans le Setting |
| `last_version` | integer \| null | Dernière version disponible configurée dans le Setting |
| `download_link` | string \| null | Lien de téléchargement de l'APK configuré dans le Setting |

---

## Response Errors

### 400 Bad Request - Validation échouée

```json
{
  "version": ["La version doit être un nombre positif."]
}
```

**Ou si la version est manquante :**

```json
{
  "version": ["Ce champ est requis."]
}
```

### 503 Service Unavailable - Configuration non disponible

```json
{
  "error": "Configuration non disponible"
}
```

**Condition :** Aucun objet `Setting` n'existe dans la base de données.

---

## Logique de Validation

### Règles de comparaison

1. **Version valide** : `current_version >= min_version` (si `min_version` est défini)
2. **Mise à jour obligatoire** : `current_version < min_version` (si `min_version` est défini)
3. **Mise à jour disponible** : `current_version < last_version` (si `last_version` est défini)

### Comportement selon les cas

| Version Utilisateur | min_version | last_version | Résultat |
|-------------------|-------------|--------------|----------|
| 10 | 5 | 10 | ✅ Valide, pas de mise à jour |
| 8 | 5 | 10 | ✅ Valide, mise à jour optionnelle |
| 3 | 5 | 10 | ❌ Invalide, mise à jour obligatoire |
| 5 | null | null | ✅ Valide (pas de contrainte) |

---

## Exemples d'Utilisation

### Exemple 1 : Vérifier la version actuelle

```bash
curl -X POST https://api.example.com/mobcash/validate-version \
  -H "Content-Type: application/json" \
  -d '{
    "version": 8
  }'
```

**Réponse :**
```json
{
  "valid": true,
  "update_required": false,
  "update_available": true,
  "current_version": 8,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

### Exemple 2 : Version obsolète nécessitant une mise à jour

```bash
curl -X POST https://api.example.com/mobcash/validate-version \
  -H "Content-Type: application/json" \
  -d '{
    "version": 3
  }'
```

**Réponse :**
```json
{
  "valid": false,
  "update_required": true,
  "update_available": true,
  "current_version": 3,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

### Exemple 3 : Version à jour

```bash
curl -X POST https://api.example.com/mobcash/validate-version \
  -H "Content-Type: application/json" \
  -d '{
    "version": 10
  }'
```

**Réponse :**
```json
{
  "valid": true,
  "update_required": false,
  "update_available": false,
  "current_version": 10,
  "min_version": 5,
  "last_version": 10,
  "download_link": "https://example.com/app.apk"
}
```

---

## Intégration dans l'Application Mobile

### Recommandations d'implémentation

1. **Au démarrage de l'application** : Appeler cette API pour vérifier la version
2. **Si `update_required = true`** : 
   - Afficher une modal bloquante avec le message de mise à jour obligatoire
   - Rediriger vers le `download_link` ou le Play Store
   - Empêcher l'utilisation de l'application jusqu'à la mise à jour
3. **Si `update_available = true` et `update_required = false`** :
   - Afficher une notification non-bloquante proposant la mise à jour
   - Permettre à l'utilisateur de continuer ou de mettre à jour
4. **Si `update_available = false`** :
   - Aucune action nécessaire, l'application est à jour

### Exemple de code (pseudo-code)

```javascript
async function checkVersion() {
  const currentVersion = getAppVersion(); // Ex: 8
  const response = await fetch('/mobcash/validate-version', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: currentVersion })
  });
  
  const data = await response.json();
  
  if (data.update_required) {
    // Mise à jour obligatoire
    showBlockingModal('Mise à jour requise', data.download_link);
  } else if (data.update_available) {
    // Mise à jour optionnelle
    showOptionalUpdateDialog('Nouvelle version disponible', data.download_link);
  }
}
```

---

## Notes Importantes

### Configuration dans le Setting

Pour que cette API fonctionne correctement, les champs suivants doivent être configurés dans le modèle `Setting` :

- **`min_version`** : Version minimum requise (obligatoire pour forcer les mises à jour)
- **`last_version`** : Dernière version disponible (pour proposer les mises à jour optionnelles)
- **`dowload_apk_link`** : Lien de téléchargement de l'APK (retourné dans la réponse)

### Gestion des valeurs nulles

- Si `min_version` est `null`, aucune version n'est considérée comme invalide
- Si `last_version` est `null`, aucune mise à jour optionnelle n'est proposée
- Si les deux sont `null`, l'API retourne `valid: true` et aucune mise à jour n'est requise

### Sécurité

- Cette API est publique (pas d'authentification requise) pour permettre la vérification avant la connexion
- Aucune information sensible n'est exposée dans la réponse

---

## Support

Pour toute question ou problème concernant cette API, contactez l'équipe de développement.

