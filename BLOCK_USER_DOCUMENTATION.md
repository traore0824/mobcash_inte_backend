# Block / Unblock User API

## Overview

This endpoint allows an admin to block or unblock a user account. It acts as a **toggle** — calling it on a blocked user will unblock them, and calling it on an active user will block them.

When a user is **blocked**:
- Their `is_block` flag is set to `True`
- All their existing JWT tokens are **immediately blacklisted** — they cannot use any active session
- Any attempt to log in will be rejected with an error message
- Any attempt to refresh their token will be rejected with `401 Unauthorized`

When a user is **unblocked**:
- Their `is_block` flag is set to `False`
- They can log in again normally to obtain new tokens

---

## Endpoint

```
POST /auth/users/block/block
```

> Note: The route `/auth/users/block/deblock` points to the same view and behaves identically (toggle).

---

## Authentication

Requires a valid **admin** JWT access token.

```
Authorization: Bearer <admin_access_token>
```

---

## Request

### Headers

| Header          | Value                        | Required |
|-----------------|------------------------------|----------|
| Authorization   | `Bearer <admin_access_token>`| Yes      |
| Content-Type    | `application/json`           | Yes      |

### Body

```json
{
  "user_id": 42
}
```

| Field     | Type    | Required | Description              |
|-----------|---------|----------|--------------------------|
| `user_id` | integer | Yes      | The ID of the user to block or unblock |

---

## Responses

### Block success — `200 OK`

Returned when the user was active and has now been blocked. All their tokens are invalidated.

```json
{
  "blocked": true
}
```

### Unblock success — `200 OK`

Returned when the user was already blocked and has now been unblocked.

```json
{
  "blocked": false
}
```

### User not found — `404 Not Found`

```json
{}
```

### Unauthorized — `401 Unauthorized`

Returned if the token is missing or invalid.

### Forbidden — `403 Forbidden`

Returned if the authenticated user is not an admin.

---

## Behavior After Blocking

| Action                  | Result                                      |
|-------------------------|---------------------------------------------|
| Login attempt           | `400 Bad Request` — "Votre compte est bloqué pour fraude" |
| Use existing access token | Rejected — token is blacklisted            |
| Refresh token           | `401 Unauthorized` — user is blocked        |

---

## Example

### Block a user

```bash
curl -X POST https://your-api.com/auth/users/block/block \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 42}'
```

**Response:**
```json
{
  "blocked": true
}
```

### Unblock the same user

```bash
curl -X POST https://your-api.com/auth/users/block/block \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 42}'
```

**Response:**
```json
{
  "blocked": false
}
```
