# Flutter Massage Therapist Dashboard Guide

## Overview

The Massage Therapist Dashboard provides tools for **massage preferences**, **session tracking**, **health disclosures**, and **technique documentation**. Focused on massage-related services.

---

## API Constants

```dart
// Massage Therapist Dashboard Endpoints 💆
static const String massageDashboard = '$_baseUrl/api/massage/dashboard/';
static const String massageClientProfiles = '$_baseUrl/api/massage/client-profiles/';
static String massageClientProfileDetail(int id) => '$_baseUrl/api/massage/client-profiles/$id/';
static const String massageHealthDisclosures = '$_baseUrl/api/massage/health-disclosures/';
static const String massageSessionNotes = '$_baseUrl/api/massage/session-notes/';

// Client self-service
static const String myMassageProfile = '$_baseUrl/api/my-massage-profile/';
static const String myHealthDisclosure = '$_baseUrl/api/my-health-disclosure/';  // Shared
```

---

## Aggregated Dashboard

**GET** `/api/massage/dashboard/`

```json
{
  "today_appointments_count": 5,
  "week_appointments_count": 18,
  "today_revenue": 650.00,
  "client_profiles_count": 32,
  "disclosure_alerts": [
    {
      "client_name": "John Doe",
      "client_id": 42,
      "booking_id": 123,
      "has_conditions": true,
      "pregnant_or_nursing": false,
      "areas_to_avoid": "Lower back (injury)"
    }
  ],
  "recent_session_notes": [
    {
      "id": 1,
      "client_name": "John Doe",
      "technique_used": "deep_tissue",
      "technique_display": "Deep Tissue",
      "created_at": "2025-12-18T10:00:00Z"
    }
  ]
}
```

---

## Client Massage Profile

**GET** `/api/massage/client-profiles/`

```json
{
  "id": 1,
  "client_name": "John Doe",
  "pressure_preference": "firm",
  "pressure_display": "Firm",
  "areas_to_focus": "Shoulders, neck, upper back",
  "areas_to_avoid": "Lower back (herniated disc)",
  "has_injuries": true,
  "injury_details": "L4-L5 herniated disc, recovering",
  "has_chronic_conditions": false,
  "chronic_conditions": "",
  "preferred_techniques": ["deep_tissue", "trigger_point"],
  "temperature_preference": "warm",
  "music_preference": "nature sounds",
  "aromatherapy_preference": "lavender"
}
```

**Client Self-Service:** `GET/POST/PATCH /api/my-massage-profile/?shop_id=5`

---

## Session Note

**GET** `/api/massage/session-notes/?booking=123`

```json
{
  "id": 1,
  "client_name": "John Doe",
  "booking": 123,
  "booking_date": "2025-12-18T10:00:00Z",
  "service_title": "Deep Tissue Massage",
  "technique_used": "deep_tissue",
  "technique_display": "Deep Tissue",
  "pressure_applied": "firm",
  "areas_worked": "Shoulders, neck, upper back",
  "tension_observations": "Significant knots in trapezius",
  "recommendations": "Stretch daily, heat therapy",
  "next_session_notes": "Focus on IT band next time",
  "duration_minutes": 60
}
```

---

## Health Disclosure (Massage-focused)

**GET** `/api/massage/health-disclosures/?client=42`

```json
{
  "id": 1,
  "client_name": "John Doe",
  "has_medical_conditions": true,
  "conditions_detail": "Herniated disc L4-L5",
  "current_medications": "Ibuprofen as needed",
  "allergies": "None",
  "pregnant_or_nursing": false,
  "recent_surgeries": "",
  "pressure_preference": "firm",
  "areas_to_avoid": "Lower back",
  "areas_to_focus": "Shoulders, neck",
  "acknowledged": true
}
```

---

## Summary

| Endpoint | Methods | Who |
|----------|---------|-----|
| `/api/massage/dashboard/` | GET | Owner |
| `/api/massage/client-profiles/` | CRUD | Owner |
| `/api/massage/health-disclosures/` | CRUD | Owner |
| `/api/massage/session-notes/` | CRUD | Owner |
| `/api/my-massage-profile/` | GET/POST/PATCH | Client |
| `/api/my-health-disclosure/` | GET/POST/PATCH | Client (shared) |
