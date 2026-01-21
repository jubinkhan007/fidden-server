# Fitness Trainer - Flutter Integration Guide

**Version:** 1.0  
**Date:** 2026-01-20  
**Backend Status:** ✅ Deployed

This guide documents the backend APIs for the **Fitness Trainer** niche dashboard.

---

## Table of Contents
1. [Dashboard Overview](#1-dashboard-overview)
2. [Calendar Session Types](#2-calendar-session-types)
3. [Fitness Packages API](#3-fitness-packages-api)
4. [Workout Templates API](#4-workout-templates-api)
5. [Nutrition Plans API](#5-nutrition-plans-api)
6. [Shop Cancellation Policy](#6-shop-cancellation-policy)

---

## 1. Dashboard Overview

### Endpoint
```
GET /api/fitness/dashboard/
Authorization: Bearer <owner_token>
```

### Response
```json
{
  "weekly_schedule": {
    "classes": 5,
    "one_to_one": 12,
    "total": 17
  },
  "revenue": {
    "paid_total": 2500.00,
    "pending_deposit_count": 3
  },
  "packages": {
    "active_count": 8
  },
  "shop_settings": {
    "cancellation_policy_enabled": true,
    "free_cancellation_hours": 24
  }
}
```

### Field Descriptions
| Field | Type | Description |
|-------|------|-------------|
| `weekly_schedule.classes` | int | Bookings for services with `capacity > 1` in the next 7 days |
| `weekly_schedule.one_to_one` | int | Bookings for 1:1 services in the next 7 days |
| `revenue.paid_total` | decimal | Sum of all succeeded payments |
| `revenue.pending_deposit_count` | int | Bookings awaiting deposit payment |
| `packages.active_count` | int | Active fitness packages with remaining sessions |

---

## 2. Calendar Session Types

The existing `/api/calendar/` endpoint now includes a `session_type` field for fitness trainers.

### Enhanced Response
```json
{
  "id": 123,
  "event_type": "booking",
  "title": "Yoga Class - Alice",
  "session_type": "class",
  "start_at": "2026-01-21T09:00:00-05:00",
  "end_at": "2026-01-21T10:00:00-05:00",
  "calendar_status": "CONFIRMED",
  "badges": ["PAID"],
  "customer": {
    "id": 45,
    "name": "Alice Johnson"
  },
  "service": {
    "id": 12,
    "title": "Yoga Class"
  }
}
```

### Session Type Values
| Value | Condition | Description |
|-------|-----------|-------------|
| `"class"` | `Service.capacity > 1` | Group class/session |
| `"1to1"` | `Service.capacity == 1` | Personal training session |
| `null` | Event is `blocked` | Not applicable for blocked time |

---

## 3. Fitness Packages API

Manages session bundles purchased by clients.

### List Packages
```
GET /api/fitness/packages/
Authorization: Bearer <owner_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "shop": 5,
    "customer": 42,
    "total_sessions": 10,
    "sessions_remaining": 7,
    "price": "500.00",
    "expires_at": "2026-03-20T23:59:59Z",
    "created_at": "2026-01-20T10:00:00Z",
    "is_active": true
  }
]
```

### Create Package
```
POST /api/fitness/packages/
Authorization: Bearer <owner_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "customer": 42,
  "total_sessions": 10,
  "sessions_remaining": 10,
  "price": "500.00",
  "expires_at": "2026-03-20T23:59:59Z"
}
```

> **Note:** `shop` is automatically set from the authenticated owner's shop.

### Update Package
```
PATCH /api/fitness/packages/{id}/
Authorization: Bearer <owner_token>
```

**Request Body:**
```json
{
  "sessions_remaining": 5,
  "is_active": false
}
```

### Delete Package
```
DELETE /api/fitness/packages/{id}/
Authorization: Bearer <owner_token>
```

### Field Reference
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `customer` | int | ✅ | User ID of the client |
| `total_sessions` | int | ✅ | Total sessions in the package |
| `sessions_remaining` | int | ✅ | Sessions still available |
| `price` | decimal | ✅ | Package price |
| `expires_at` | datetime | ❌ | Optional expiration date (ISO 8601) |
| `is_active` | bool | ❌ | Default: `true` |

### Auto-Decrement Behavior
When a booking is marked as **completed** (via the `complete_past_bookings` task), the system automatically decrements `sessions_remaining` for the customer's oldest active package at that shop.

---

## 4. Workout Templates API

Stores reusable workout routines.

### List Templates
```
GET /api/fitness/workout-templates/
Authorization: Bearer <owner_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "shop": 5,
    "title": "Leg Day",
    "description": "Intense lower body workout",
    "exercises": [
      {"name": "Squats", "sets": 4, "reps": 12, "weight": "bodyweight"},
      {"name": "Lunges", "sets": 3, "reps": 10, "weight": "20lb dumbbells"},
      {"name": "Deadlifts", "sets": 4, "reps": 8, "weight": "135lb"}
    ],
    "created_at": "2026-01-20T10:00:00Z",
    "updated_at": "2026-01-20T10:00:00Z"
  }
]
```

### Create Template
```
POST /api/fitness/workout-templates/
Authorization: Bearer <owner_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "title": "Upper Body Push",
  "description": "Chest, shoulders, triceps",
  "exercises": [
    {"name": "Bench Press", "sets": 4, "reps": 10},
    {"name": "Overhead Press", "sets": 3, "reps": 12},
    {"name": "Tricep Dips", "sets": 3, "reps": 15}
  ]
}
```

### Update Template
```
PATCH /api/fitness/workout-templates/{id}/
```

### Delete Template
```
DELETE /api/fitness/workout-templates/{id}/
```

### Exercises JSON Schema
The `exercises` field is a flexible JSON array. Recommended structure:
```json
{
  "name": "string (required)",
  "sets": "int (optional)",
  "reps": "int or string (optional, e.g. '8-12')",
  "weight": "string (optional)",
  "duration": "string (optional, e.g. '30 seconds')",
  "notes": "string (optional)"
}
```

---

## 5. Nutrition Plans API

Stores diet guidelines and external resource links.

### List Plans
```
GET /api/fitness/nutrition-plans/
Authorization: Bearer <owner_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "shop": 5,
    "title": "Keto Diet Plan",
    "notes": "Low carb, high fat diet. Avoid sugars and grains.",
    "external_links": [
      "https://example.com/keto-guide",
      "https://example.com/meal-prep-tips"
    ],
    "created_at": "2026-01-20T10:00:00Z",
    "updated_at": "2026-01-20T10:00:00Z"
  }
]
```

### Create Plan
```
POST /api/fitness/nutrition-plans/
Authorization: Bearer <owner_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "title": "High Protein Diet",
  "notes": "Focus on lean meats, eggs, and legumes",
  "external_links": [
    "https://example.com/protein-guide"
  ]
}
```

### Update Plan
```
PATCH /api/fitness/nutrition-plans/{id}/
```

### Delete Plan
```
DELETE /api/fitness/nutrition-plans/{id}/
```

### Field Reference
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ✅ | Plan name (max 255 chars) |
| `notes` | text | ❌ | Free-form diet notes |
| `external_links` | array | ❌ | List of URL strings |

---

## 6. Shop Cancellation Policy

Two new fields on the Shop model for fitness-specific cancellation settings.

### Fields in Shop Response
```json
{
  "id": 5,
  "name": "Bob's Gym",
  "cancellation_policy_enabled": true,
  "cancellation_policy_text": "24-hour cancellation required. Late cancellations forfeit deposit.",
  "free_cancellation_hours": 24,
  "cancellation_fee_percentage": 50
}
```

### Field Descriptions
| Field | Type | Description |
|-------|------|-------------|
| `cancellation_policy_enabled` | bool | Whether to enforce the policy |
| `cancellation_policy_text` | string | Custom policy text (nullable) |
| `free_cancellation_hours` | int | Hours before appointment for free cancellation |
| `cancellation_fee_percentage` | int | Fee percentage for late cancellations |

### Update via Shop PATCH
```
PATCH /api/shop/{id}/
Authorization: Bearer <owner_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "cancellation_policy_enabled": true,
  "cancellation_policy_text": "Minimum 24 hours notice required for cancellations."
}
```

---

## Error Responses

All endpoints return standard error formats:

### 400 Bad Request
```json
{
  "title": ["This field is required."]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

---

## Phase 2B (Upcoming)

The following features are planned for the next phase:

| Feature | Description |
|---------|-------------|
| `FitnessClientProfile` | Client-specific fitness data (goals, measurements) |
| `ClientProgressEntry` | Progress tracking with photo uploads |
| `PreSessionQuestionnaire` | Pre-workout health/readiness forms |

---

## Questions?

Contact the backend team for any clarification on these endpoints.
