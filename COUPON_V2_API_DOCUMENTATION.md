# API Documentation — Coupon System V2

> Base URL: `https://api.slaterci.net/mobcash`  
> Authentication: `Authorization: Bearer <access_token>`  
> Format: JSON

---

## Table of Contents

1. [List / Create a coupon](#1-list--create-a-coupon)
2. [Coupon detail](#2-coupon-detail)
3. [Vote on a coupon (like / dislike)](#3-vote-on-a-coupon)
4. [Coupon wallet](#4-coupon-wallet)
5. [Withdraw from coupon wallet](#5-withdraw-from-coupon-wallet)
6. [Author comments](#6-author-comments)
7. [Edit / Delete a comment](#7-edit--delete-a-comment)
8. [Vote for an author](#8-vote-for-an-author)
9. [Author stats](#9-author-stats)
10. [My coupon stats](#10-my-coupon-stats)
11. [Important business rules](#11-important-business-rules)
12. [Error codes](#12-error-codes)

---

## 1. List / Create a coupon

### `GET /v2/coupons`

Returns coupons published in the **last 24 hours**.

**Auth required**: No (public)

**Query params**

| Parameter | Type | Required | Description                        |
|-----------|------|----------|------------------------------------|
| bet_app   | UUID | No       | Filter by bookmaker app            |
| page      | int  | No       | Page number (default: 1)           |
| page_size | int  | No       | Page size (max: 50)                |

**Response 200**

```json
{
  "count": 12,
  "next": "https://api.slaterci.net/mobcash/v2/coupons?page=2",
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

---

### `POST /v2/coupons`

Publish a new coupon.

**Auth required**: Yes — user with `can_publish_coupons = true` or admin

**Body**

| Field       | Type    | Required | Description                                           |
|-------------|---------|----------|-------------------------------------------------------|
| bet_app_id  | UUID    | Yes      | Bookmaker app ID                                      |
| code        | string  | No       | Coupon code (must be unique per app)                  |
| coupon_type | string  | No       | `single`, `combine`, `system` — default: `combine`    |
| cote        | decimal | No       | Total odds — default: `1.00`                          |
| match_count | int     | No       | Number of matches — default: `1`                      |

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

**Response 201**: full coupon object (same structure as GET)

**Possible errors**

| Code | Message                                                      |
|------|--------------------------------------------------------------|
| 403  | The coupon system is disabled                                |
| 403  | You are not authorized to publish coupons                    |
| 404  | Bookmaker app not found                                      |
| 400  | This promo code already exists for this bookmaker app        |
| 429  | You already created a coupon for this app today              |
| 429  | Daily quota reached (configurable in Settings)               |
| 429  | Weekly quota reached (configurable in Settings)              |

> **Combine rule**: if `coupon_type = "combine"`, `match_count` must be >= 2.

---

## 2. Coupon detail

### `GET /v2/coupons/{id}`

**Auth required**: No (public)

**Response 200**: full coupon object (same structure as list)

### `PUT/PATCH /v2/coupons/{id}`

**Auth required**: Admin only

### `DELETE /v2/coupons/{id}`

**Auth required**: Admin only

---

## 3. Vote on a coupon

### `POST /v2/coupons/{id}/vote`

**Auth required**: Yes — user with `can_rate_coupons = true`

**Body**

| Field     | Type   | Required | Values             |
|-----------|--------|----------|--------------------|
| vote_type | string | Yes      | `like`, `dislike`  |

**Example**

```json
{
  "vote_type": "like"
}
```

**Response 200**

```json
{
  "message": "Vote like registered successfully",
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

**Vote behavior**

| Situation                   | Result                                        |
|-----------------------------|-----------------------------------------------|
| No previous vote            | Vote registered, counter incremented          |
| Same vote type again        | Vote cancelled, counter decremented           |
| Opposite vote type          | Vote changed, both counters updated           |

**Possible errors**

| Code | Message                                                        |
|------|----------------------------------------------------------------|
| 403  | You are not authorized to rate coupons                         |
| 404  | Coupon not found                                               |
| 400  | You cannot vote on your own coupon                             |
| 400  | You already voted today on a coupon from this author           |

> **Rule**: 1 vote per day per author (not per coupon — per author).

---

## 4. Coupon wallet

### `GET /v2/coupon-wallet`

Returns the wallet of the authenticated user.

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

| Field          | Description                                        |
|----------------|----------------------------------------------------|
| balance        | Available balance for withdrawal                   |
| total_earned   | Total earned since account creation                |
| pending_payout | Amount currently being processed (pending payout)  |

---

## 5. Withdraw from coupon wallet

### `POST /v2/coupon-wallet-withdraw`

**Auth required**: Yes

**Body**

| Field          | Type    | Required | Description                                  |
|----------------|---------|----------|----------------------------------------------|
| amount         | decimal | Yes      | Amount to withdraw (min: configurable)       |
| phone_number   | string  | Yes      | Phone number for mobile money payment        |
| network        | UUID    | Yes      | Mobile money network ID                      |
| bank_name      | string  | No       | Bank name (optional)                         |
| account_number | string  | No       | Account number (optional)                    |
| account_holder | string  | No       | Account holder name (optional)               |

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

| Code | Message                                              |
|------|------------------------------------------------------|
| 400  | Minimum withdrawal amount: X FCFA                    |
| 400  | Insufficient balance. Available balance: X FCFA      |
| 404  | Payment network not found                            |

---

## 6. Author comments

### `GET /v2/author-comments?coupon_author_id={uuid}`

Returns comments (with replies) on an author.

**Auth required**: Yes

**Query params**

| Parameter        | Type | Required | Description         |
|------------------|------|----------|---------------------|
| coupon_author_id | UUID | Yes      | Target author ID    |

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

Post a comment or a reply.

**Auth required**: Yes

**Body**

| Field     | Type   | Required | Description                                    |
|-----------|--------|----------|------------------------------------------------|
| coupon_id | UUID   | Yes      | ID of the related coupon                       |
| content   | string | Yes      | Comment content (max 5000 characters)          |
| parent_id | UUID   | No       | Parent comment ID (for a reply)                |

**Example**

```json
{
  "coupon_id": "550e8400-...",
  "content": "Excellent pick, I'm following!",
  "parent_id": null
}
```

**Response 201**: full comment object

---

## 7. Edit / Delete a comment

### `PATCH /v2/author-comments/{id}`

Edit your own comment.

**Auth required**: Yes (comment author only)

**Body**

```json
{
  "content": "Updated comment content"
}
```

**Response 200**: updated comment object

---

### `DELETE /v2/author-comments/{id}`

Soft delete — the comment stays in the database with `is_deleted = true`.

**Auth required**: Yes (comment author only)

**Response 200**

```json
{
  "message": "Comment deleted successfully."
}
```

---

## 8. Vote for an author

### `POST /v2/author-ratings`

Vote on an author's reputation via one of their coupons.

**Auth required**: Yes

**Body**

| Field     | Type    | Required | Description                          |
|-----------|---------|----------|--------------------------------------|
| coupon_id | UUID    | Yes      | ID of the target author's coupon     |
| is_like   | boolean | Yes      | `true` = like, `false` = dislike     |

**Example**

```json
{
  "coupon_id": "550e8400-...",
  "is_like": true
}
```

**Response 201 / 200**

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

| Code | Message                                  |
|------|------------------------------------------|
| 404  | Coupon not found                         |
| 400  | You cannot vote for yourself             |

> **Note**: 1 vote per author (unique on `user` + `coupon_author`). Voting again updates the existing vote.

---

## 9. Author stats

### `GET /v2/author-stats/{user_id}`

**Auth required**: Yes

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

| Field         | Description                                          |
|---------------|------------------------------------------------------|
| author_rating | Score out of 5 calculated as: `(likes / total_votes) * 5` |

---

## 10. My coupon stats

### `GET /v2/user/coupon-stats`

Stats for the authenticated user.

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

### Publishing access

To publish a coupon, the user must have `can_publish_coupons = true` on their account (or be an admin). Contact the admin to enable this permission.

### Voting access

To vote on a coupon, the user must have `can_rate_coupons = true` on their account.

### Publishing quotas (configurable by admin)

| Rule                           | Default value |
|--------------------------------|---------------|
| Max coupons per day            | 10            |
| Max coupons per week           | 50            |
| 1 coupon per app per day       | Yes (fixed)   |
| Unique code per app            | Yes (fixed)   |

### Monetization (enabled by admin)

When `enable_coupon_monetization = true`:
- Each like received credits the author's wallet by `monetization_amount` FCFA
- Each dislike debits `monetization_amount` FCFA
- Changing a vote = double adjustment

### Coupon visibility

- Coupons are visible for **24 hours** after creation
- After that, they no longer appear in the list

### Wallet withdrawal

- Minimum amount: configurable (`minimum_coupon_withdrawal`, default 1000 FCFA)
- Withdrawal triggers a mobile money payment via Connect Pro

---

## 12. Error codes

| HTTP Code | Meaning                                          |
|-----------|--------------------------------------------------|
| 400       | Invalid data or business rule not respected      |
| 401       | Missing or expired token                         |
| 403       | Insufficient permissions                         |
| 404       | Resource not found                               |
| 429       | Quota exceeded (too many coupons)                |
| 500       | Internal server error                            |

---

## Endpoints summary

| Method | Endpoint                       | Auth         | Description                      |
|--------|--------------------------------|--------------|----------------------------------|
| GET    | /v2/coupons                    | No           | List coupons (last 24h)          |
| POST   | /v2/coupons                    | Yes*         | Publish a coupon                 |
| GET    | /v2/coupons/{id}               | No           | Coupon detail                    |
| PUT    | /v2/coupons/{id}               | Admin        | Update a coupon                  |
| DELETE | /v2/coupons/{id}               | Admin        | Delete a coupon                  |
| POST   | /v2/coupons/{id}/vote          | Yes*         | Like / dislike a coupon          |
| GET    | /v2/coupon-wallet              | Yes          | My wallet                        |
| POST   | /v2/coupon-wallet-withdraw     | Yes          | Withdraw my earnings             |
| GET    | /v2/coupon-wallet-payouts      | Admin        | List payouts                     |
| GET    | /v2/author-comments            | Yes          | Comments on an author            |
| POST   | /v2/author-comments            | Yes          | Post a comment                   |
| PATCH  | /v2/author-comments/{id}       | Yes (author) | Edit my comment                  |
| DELETE | /v2/author-comments/{id}       | Yes (author) | Delete my comment                |
| POST   | /v2/author-ratings             | Yes          | Vote for an author               |
| GET    | /v2/author-stats/{user_id}     | Yes          | Author stats                     |
| GET    | /v2/user/coupon-stats          | Yes          | My coupon stats                  |

> `*` = requires a specific flag on the account (`can_publish_coupons` or `can_rate_coupons`)
