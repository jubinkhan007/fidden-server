# Flutter Esthetician Dashboard Guide

## Overview

The Esthetician Dashboard provides tools for **skin profiles**, **skincare regimens**, **treatment tracking**, and **retail products**. Focused on skincare-related services.

---

## API Constants

```dart
// Esthetician Dashboard Endpoints 🧖‍♀️
static const String estheticianDashboard = '$_baseUrl/api/esthetician/dashboard/';
static const String estheticianClientProfiles = '$_baseUrl/api/esthetician/client-profiles/';
static String estheticianClientProfileDetail(int id) => '$_baseUrl/api/esthetician/client-profiles/$id/';
static const String estheticianHealthDisclosures = '$_baseUrl/api/esthetician/health-disclosures/';
static const String estheticianTreatmentNotes = '$_baseUrl/api/esthetician/treatment-notes/';
static const String estheticianRetailProducts = '$_baseUrl/api/esthetician/retail-products/';

// Client self-service
static const String mySkinProfile = '$_baseUrl/api/my-skin-profile/';
static const String myHealthDisclosure = '$_baseUrl/api/my-health-disclosure/';
```

---

## Aggregated Dashboard

**GET** `/api/esthetician/dashboard/`

```json
{
  "today_appointments_count": 5,
  "week_appointments_count": 18,
  "today_revenue": 850.00,
  "client_profiles_count": 45,
  "retail_products_count": 12,
  "disclosure_alerts": [
    {
      "client_name": "Jane Doe",
      "client_id": 42,
      "booking_id": 123,
      "has_conditions": true,
      "pregnant_or_nursing": false
    }
  ],
  "recent_treatment_notes": [
    {
      "id": 1,
      "client_name": "Jane Doe",
      "treatment_type": "facial",
      "treatment_type_display": "Facial",
      "created_at": "2025-12-18T10:00:00Z"
    }
  ]
}
```

---

## Client Skin Profile

**GET** `/api/esthetician/client-profiles/`

```json
{
  "id": 1,
  "client_name": "Jane Doe",
  "skin_type": "combination",
  "skin_type_display": "Combination",
  "primary_concerns": ["acne", "aging"],
  "allergies": "Salicylic acid",
  "sensitivities": "Fragrance",
  "current_products": "CeraVe, The Ordinary",
  "morning_routine": [{"step": 1, "product": "Cleanser"}, {"step": 2, "product": "Serum"}],
  "evening_routine": [],
  "weekly_treatments": [],
  "regimen_notes": "Start retinol gradually"
}
```

**Client Self-Service:** `GET/POST/PATCH /api/my-skin-profile/?shop_id=5`

---

## Treatment Note

**GET** `/api/esthetician/treatment-notes/?booking=123`

```json
{
  "id": 1,
  "client_name": "Jane Doe",
  "booking": 123,
  "treatment_type": "facial",
  "treatment_type_display": "Facial",
  "products_used": "CeraVe Cleanser, Glow Recipe Toner",
  "observations": "Mild congestion on T-zone",
  "recommendations": "Weekly exfoliation",
  "before_photo_url": "https://...",
  "after_photo_url": "https://..."
}
```

---

## Retail Product

**GET** `/api/esthetician/retail-products/?category=serum`

```json
{
  "id": 1,
  "name": "Vitamin C Serum",
  "brand": "The Ordinary",
  "category": "serum",
  "price": "12.99",
  "in_stock": true,
  "image_url": "https://...",
  "purchase_link": "https://..."
}
```

---

## Summary

| Endpoint | Methods | Who |
|----------|---------|-----|
| `/api/esthetician/dashboard/` | GET | Owner |
| `/api/esthetician/client-profiles/` | CRUD | Owner |
| `/api/esthetician/health-disclosures/` | CRUD | Owner |
| `/api/esthetician/treatment-notes/` | CRUD | Owner |
| `/api/esthetician/retail-products/` | CRUD | Owner |
| `/api/my-skin-profile/` | GET/POST/PATCH | Client |
| `/api/my-health-disclosure/` | GET/POST/PATCH | Client |
