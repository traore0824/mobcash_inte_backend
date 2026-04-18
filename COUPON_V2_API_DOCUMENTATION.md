# API Documentation — Coupon System V2

> Base URL: `https://dev.slaterci.net/mobcash`
> Authentication: `Authorization: Bearer <access_token>`
> Format: JSON

---

## Table of Contents

1. [List / Create a coupon](#1-list--create-a-coupon)
2. [Coupon detail](#2-coupon-detail)
3. [Vote on a coupon](#3-vote-on-a-coupon)
4. [Coupon wallet](#4-coupon-wallet)
5. [Withdraw from coupon wallet](#5-withdraw-from-coupon-wallet)
6. [Author comments](#6-author-comments)
7. [Edit / Delete a comment](#7-edit--delete-a-comment)
8. [Vote for an author](#8-vote-for-an-author)
9. [Author stats](#9-author-stats)
10. [My coupon stats](#10-my-coupon-stats)
11. [Important business rules](#11-important-business-rules)
12. [Error codes](#12-error-codes)
13. [Endpoints summary](#13-endpoints-summary)

---

## 1. List / Create a coupon

### `GET /v2/coupons`

Returns coupons published in the **last 24 hours**. After 24h a coupon no longer appears in this list.

**Auth required**: No (public)

**Query params**

| Parameter | Type   | Required | Description                      |
|-----------|--------|----------|----------------------------------|
| bet_app   | UUID   | No       | Filter by bookmaker app ID       |
| page      | int    | No       | Page number (default: 1)         |
| page_size | int    | No       | Page size (max: 50)              |

**Response 200**

```json
{
  "count": 12,
  "next": "https://dev.slaterci.net/mobcash/v2/coupons?page=2",
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-04-16T10:30:00Z",
      "bet_app": "uuid-of-the-app",
      "bet_app_details": {
        "id": "uuid-of-the-app",
        "name": "1xBet"
      },
      "code": "ABC123",
      "author": "uuid-author",
      "author_name": "John Doe",
      "author_rating": 4.2,
      "author_coupon_points": 15.0,
      "coupon_type": "combine",
      "cote": "3.50",
      "match_count": 4,
      "potential_gain": "35000.00",
      "likes_count": 12,
      "dislikes_count": 2,
      "total_ratings": 14,
      "user_liked": false,
      "user_disliked": false
    }
  ]
}
```

> `user_liked` and `user_disliked` are always `false` on unauthenticated requests.

---

### `POST /v2/coupons`

Publish a new coupon.

**Auth required**: Yes — user with `can_publish_coupons = true` OR admin (`is_staff = true`)

**Body**

| Field       | Type    | Required | Accepted values                          | Description                        |
|-------------|---------|----------|------------------------------------------|------------------------------------|
| bet_app_id  | UUID    | Yes      | Any valid AppName UUID                   | Bookmaker app ID                   |
| code        | string  | No       | Any string, unique per app               | Coupon code                        |
| coupon_type | string  | No       | `"single"`, `"combine"`, `"system"`      | Default: `"combine"`               |
| cote        | decimal | No       | Any positive decimal (max 6 digits, 2dp) | Total odds — default: `1.00`       |
| match_count | int     | No       | Integer >= 1 (>= 2 if combine)           | Number of matches — default: `1`   |

> `potential_gain` is calculated automatically by the server (`cote * 10000`). Do NOT send it.

**Example**

```json
{
  "bet_app_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "TOP-PICK",
  "coupon_type": "combine",
  "cote": 4.50,
  "match_count": 5
}
```

**Response 201**: full coupon object (same structure as GET list item)

**Possible errors**

| Code | Error key | Message                                                        |
|------|-----------|----------------------------------------------------------------|
| 403  | `error`   | `"Le système de coupons est désactivé."`                       |
| 403  | `error`   | `"Vous n'avez pas l'autorisation de publier des coupons."`     |
| 404  | `error`   | `"Application bookmaker non trouvée."`                         |
| 400  | `error`   | `"Ce code promo existe déjà pour cette application bookmaker."`|
| 400  | `match_count` | `"Un coupon combiné doit avoir au moins 2 matchs."`        |
| 429  | `error`   | `"Vous avez déjà créé un coupon pour {app} aujourd'hui."`      |
| 429  | `error`   | `"Quota journalier de {N} coupons atteint."`                   |
| 429  | `error`   | `"Quota hebdomadaire de {N} coupons atteint."`                 |

---

## 2. Coupon detail

### `GET /v2/coupons/{id}`

**Auth required**: No (public)

**Response 200**: full coupon object (same structure as list item)

### `PUT / PATCH /v2/coupons/{id}`

**Auth required**: Admin only (`is_staff = true`)

### `DELETE /v2/coupons/{id}`

**Auth required**: Admin only (`is_staff = true`)

---

## 3. Vote on a coupon

### `POST /v2/coupons/{id}/vote`

**Auth required**: Yes — user with `can_rate_coupons = true` (admins are NOT exempt from this rule)

**Body**

| Field     | Type   | Required | Accepted values              |
|-----------|--------|----------|------------------------------|
| vote_type | string | Yes      | `"like"` or `"dislike"` only |

> Any other value (`"lose"`, `"win"`, `"up"`, etc.) returns:
> ```json
> {"vote_type": ["\"lose\" is not a valid choice."]}
> ```

**Example**

```json
{
  "vote_type": "like"
}
```

**Response 200**

```json
{
  "message": "Vote like enregistré avec succès",
  "coupon": {
    "id": "550e8400-...",
    "likes": 13,
    "dislikes": 2,
    "user_liked": true,
    "user_disliked": false
  },
  "amount_earned": "1.00",
  "points_delta": 1.0
}
```

> `amount_earned` is `"0"` if monetization is disabled in settings.

**Vote behavior**

| Situation                        | Result                                              |
|----------------------------------|-----------------------------------------------------|
| No previous vote                 | Vote registered, counter incremented                |
| Same vote type sent again        | Vote cancelled, counter decremented                 |
| Opposite vote type sent          | Vote switched, both counters updated                |

**Possible errors**

| Code | Error key | Message                                                              |
|------|-----------|----------------------------------------------------------------------|
| 403  | `error`   | `"Vous n'avez pas l'autorisation de noter des coupons."`             |
| 404  | `error`   | `"Coupon non trouvé."`                                               |
| 400  | `error`   | `"Vous ne pouvez pas voter sur votre propre coupon."`                |
| 400  | `error`   | `"Vous avez déjà voté aujourd'hui sur un coupon de cet auteur."`     |

> **Rule**: 1 vote per day per **author** (not per coupon). If you already voted on any coupon from the same author today, you cannot vote again.

---

## 4. Coupon wallet

### `GET /v2/coupon-wallet`

Returns the wallet of the authenticated user. Created automatically if it doesn't exist yet.

**Auth required**: Yes

**Response 200**

```json
{
  "id": "uuid",
  "user": "uuid-user",
  "user_email": "user@example.com",
  "balance": "25.50",
  "total_earned": "50.00",
  "pending_payout": "10.00",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-04-16T10:00:00Z"
}
```

| Field          | Description                                          |
|----------------|------------------------------------------------------|
| balance        | Available balance for withdrawal                     |
| total_earned   | Total earned since account creation                  |
| pending_payout | Amount currently being processed (pending withdrawal)|

---

## 5. Withdraw from coupon wallet

### `POST /v2/coupon-wallet-withdraw`

**Auth required**: Yes

**Body**

| Field          | Type    | Required | Description                                                    |
|----------------|---------|----------|----------------------------------------------------------------|
| amount         | decimal | Yes      | Amount to withdraw — must be >= `minimum_coupon_withdrawal`    |
| phone_number   | string  | Yes      | Phone number for mobile money payment (max 20 chars)           |
| network        | UUID    | Yes      | UUID of the Network object (get it from `GET /mobcash/network`)|
| bank_name      | string  | No       | Bank name — default: `""`                                      |
| account_number | string  | No       | Account number — default: `""`                                 |
| account_holder | string  | No       | Account holder name — default: `""`                            |

**Example**

```json
{
  "amount": 2000,
  "phone_number": "22901020304",
  "network": "uuid-of-the-network"
}
```

**Response 201**: full Transaction object

**Possible errors**

| Code | Error key | Message                                                  |
|------|-----------|----------------------------------------------------------|
| 400  | `error`   | `"Montant minimum de retrait: {N} FCFA."`                |
| 400  | `error`   | `"Solde insuffisant. Solde disponible: {N} FCFA."`       |
| 404  | `error`   | `"Réseau de paiement non trouvé."`                       |

---

## 6. Author comments

### `GET /v2/author-comments?coupon_author_id={uuid}`

Returns top-level comments (with nested replies) on an author. Only non-deleted comments are returned.

**Auth required**: Yes

**Query params**

| Parameter        | Type | Required | Description          |
|------------------|------|----------|----------------------|
| coupon_author_id | UUID | Yes      | Target author's user ID |

**Response 200**

```json
[
  {
    "id": "uuid",
    "author": "uuid-comment-author",
    "author_name": "Mary Martin",
    "coupon_author": "uuid-coupon-author",
    "coupon": "uuid-coupon",
    "content": "Great pick!",
    "parent": null,
    "created_at": "2026-04-16T09:00:00Z",
    "updated_at": "2026-04-16T09:00:00Z",
    "is_deleted": false,
    "replies": [
      {
        "id": "uuid-reply",
        "author": "uuid",
        "author_name": "John Doe",
        "content": "Thanks!",
        "created_at": "2026-04-16T09:05:00Z",
        "updated_at": "2026-04-16T09:05:00Z",
        "is_deleted": false
      }
    ]
  }
]
```

---

### `POST /v2/author-comments`

Post a comment or a reply on a coupon.

**Auth required**: Yes

**Body**

| Field     | Type   | Required | Description                                      |
|-----------|--------|----------|--------------------------------------------------|
| coupon_id | UUID   | Yes      | UUID of the coupon being commented on            |
| content   | string | Yes      | Comment text (max 5000 characters)               |
| parent_id | UUID   | No       | UUID of parent comment (omit for top-level)      |

**Example — top-level comment**

```json
{
  "coupon_id": "550e8400-...",
  "content": "Excellent pick, I'm following!"
}
```

**Example — reply**

```json
{
  "coupon_id": "550e8400-...",
  "content": "I agree!",
  "parent_id": "uuid-of-parent-comment"
}
```

**Response 201**: full comment object

**Possible errors**

| Code | Error key | Message                                  |
|------|-----------|------------------------------------------|
| 400  | `error`   | `"coupon_author_id est requis."`         |
| 404  | `error`   | `"Coupon non trouvé."`                   |
| 404  | `error`   | `"Commentaire parent non trouvé."`       |

---

## 7. Edit / Delete a comment

### `PATCH /v2/author-comments/{id}`

Edit your own comment. Only the `content` field can be updated.

**Auth required**: Yes — comment author only

**Body**

```json
{
  "content": "Updated comment content"
}
```

**Response 200**: updated comment object

**Error**: returns 404 if comment not found or you are not the author.

---

### `DELETE /v2/author-comments/{id}`

Soft delete — `is_deleted` is set to `true`, the comment stays in the database.

**Auth required**: Yes — comment author only

**Response 200**

```json
{
  "message": "Commentaire supprimé avec succès."
}
```

**Error**: returns 404 if comment not found or you are not the author.

---

## 8. Vote for an author

### `POST /v2/author-ratings`

Vote on an author's overall reputation via one of their coupons.

**Auth required**: Yes

**Body**

| Field     | Type    | Required | Description                              |
|-----------|---------|----------|------------------------------------------|
| coupon_id | UUID    | Yes      | UUID of any coupon from the target author|
| is_like   | boolean | Yes      | `true` = like, `false` = dislike         |

**Example**

```json
{
  "coupon_id": "550e8400-...",
  "is_like": true
}
```

**Response 201** (new vote) or **200** (updated vote)

```json
{
  "id": "uuid",
  "user": "uuid",
  "coupon_author": "uuid",
  "coupon": "uuid",
  "is_like": true,
  "created_at": "2026-04-16T10:00:00Z",
  "updated_at": "2026-04-16T10:00:00Z"
}
```

**Possible errors**

| Code | Error key | Message                                      |
|------|-----------|----------------------------------------------|
| 404  | `error`   | `"Coupon non trouvé."`                       |
| 400  | `error`   | `"Vous ne pouvez pas voter pour vous-même."` |

> **Note**: 1 vote per author (unique on `user` + `coupon_author`). Sending again updates the existing vote — no duplicate created.

---

## 9. Author stats

### `GET /v2/author-stats/{user_id}`

**Auth required**: Yes

**URL param**: `user_id` — UUID of the author

**Response 200**

```json
{
  "user": {
    "id": "uuid",
    "email": "author@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "total_coupons": 42,
  "total_likes": 150,
  "total_dislikes": 10,
  "author_rating": 4.38
}
```

| Field         | Description                                               |
|---------------|-----------------------------------------------------------|
| author_rating | Score out of 5: `(total_likes / (total_likes + total_dislikes)) * 5` — `0.0` if no votes |

**Error**

| Code | Message                    |
|------|----------------------------|
| 404  | `"Auteur non trouvé."`     |

---

## 10. My coupon stats

### `GET /v2/user/coupon-stats`

Stats for the currently authenticated user.

**Auth required**: Yes

**Response 200**

```json
{
  "total_published_coupons": 10,
  "total_likes_received": 45,
  "total_dislikes_received": 3,
  "wallet_balance": "25.50",
  "total_earned": "50.00",
  "pending_payouts": "10.00"
}
```

---

## 11. Important business rules

### Who can publish coupons

The user must have **`can_publish_coupons = true`** on their account, OR be an admin (`is_staff = true`). This flag is set by an admin in the Django admin panel.

### Who can vote on coupons

The user must have **`can_rate_coupons = true`** on their account. Admins are **not** exempt — they also need this flag.

### Coupon system switch

The entire coupon system can be disabled globally via `coupon_enable` in Settings. When disabled, no one can create coupons and `POST /v2/coupons` returns 403.

### Publishing quotas (set by admin in Settings)

| Rule                              | Default |
|-----------------------------------|---------|
| Max coupons per day (all apps)    | 10      |
| Max coupons per week (all apps)   | 50      |
| Max 1 coupon per app per day      | Fixed   |
| Coupon code must be unique per app| Fixed   |

### Coupon visibility

Coupons are only visible for **24 hours** after creation. After that they disappear from `GET /v2/coupons`.

### Monetization (enabled by admin)

When `enable_coupon_monetization = true` in Settings:
- Each **like** received → author wallet credited by `monetization_amount` FCFA
- Each **dislike** received → author wallet debited by `monetization_amount` FCFA
- Switching vote (like → dislike or reverse) → double adjustment applied
- Cancelling a vote → adjustment reversed

When disabled, `amount_earned` in vote response is always `"0"`.

### Wallet withdrawal

- Minimum amount: `minimum_coupon_withdrawal` in Settings (default 1000 FCFA)
- Triggers a real mobile money payout via Connect Pro
- The `network` UUID must come from `GET /mobcash/network`

---

## 12. Error codes

| HTTP Code | Meaning                                          |
|-----------|--------------------------------------------------|
| 400       | Invalid data or business rule not respected      |
| 401       | Missing or expired token                         |
| 403       | Insufficient permissions or system disabled      |
| 404       | Resource not found                               |
| 429       | Publishing quota exceeded                        |
| 500       | Internal server error                            |

---

## 13. Endpoints summary

| Method | Endpoint                          | Auth              | Description                      |
|--------|-----------------------------------|-------------------|----------------------------------|
| GET    | /v2/coupons                       | No                | List coupons (last 24h)          |
| POST   | /v2/coupons                       | Yes*              | Publish a coupon                 |
| GET    | /v2/coupons/{id}                  | No                | Coupon detail                    |
| PUT    | /v2/coupons/{id}                  | Admin only        | Update a coupon                  |
| DELETE | /v2/coupons/{id}                  | Admin only        | Delete a coupon                  |
| POST   | /v2/coupons/{id}/vote             | Yes**             | Like / dislike a coupon          |
| GET    | /v2/coupon-wallet                 | Yes               | My wallet                        |
| POST   | /v2/coupon-wallet-withdraw        | Yes               | Withdraw my earnings             |
| GET    | /v2/coupon-wallet-payouts         | Admin only        | List all payouts                 |
| GET    | /v2/author-comments               | Yes               | Comments on an author            |
| POST   | /v2/author-comments               | Yes               | Post a comment or reply          |
| PATCH  | /v2/author-comments/{id}          | Yes (own only)    | Edit my comment                  |
| DELETE | /v2/author-comments/{id}          | Yes (own only)    | Delete my comment                |
| POST   | /v2/author-ratings                | Yes               | Vote for an author               |
| GET    | /v2/author-stats/{user_id}        | Yes               | Stats of an author               |
| GET    | /v2/user/coupon-stats             | Yes               | My coupon stats                  |

> `*` requires `can_publish_coupons = true` OR `is_staff = true`
> `**` requires `can_rate_coupons = true` — admins are NOT exempt
