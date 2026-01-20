# Flutter Integration Guide: Rule-Based Scheduling & Timezones

**Date:** 2026-01-13
**Version:** 1.0
**System:** Rule-Based Availability Engine

---

## 1. Overview
The backend scheduling system has been upgraded to a **Rule-Based Availability Engine**. This replaces the old "pre-generated slots" model.
Key changes:
- Slots are computed on-the-fly based on provider rules.
- **Timezones are now fully supported.** The API returns precise timezone information.
- **DST Safety.** The backend validates time existence and handles ambiguous times.

## 2. API Changes

### A. Availability Lookup (`GET /api/availability/`)

**Endpoint:** `GET /api/availability/?shop_id=1&service_id=2&date=2026-03-09`

**Old Response:**
```json
{
  "available_starts": ["09:00", "09:30"] // Naive strings
}
```

**New Response:**
```json
{
  "date": "2026-03-09",
  "shop_id": 1,
  "service_id": 2,
  "timezone_id": "America/New_York",  // <--- CRITICAL: Use this logic
  "available_slots": [
    {
      "start_at": "2026-03-09T09:00:00-05:00",      // ISO 8601 with Offset (Wall Time)
      "start_at_utc": "2026-03-09T14:00:00Z",       // UTC Time (Use for logic/sorting)
      "availability_count": 1
    },
    {
      "start_at": "2026-03-09T09:30:00-05:00",
      "start_at_utc": "2026-03-09T14:30:00Z",
      "availability_count": 1
    }
  ]
}
```

### B. Booking Creation (`POST /api/bookings/`)

**Endpoint:** `POST /api/bookings/`

**Request Payload:**
```json
{
  "shop_id": 1,
  "service_id": 2,
  "provider_id": 5, // Optional (if null, engine picks best provider)
  "start_at": "2026-03-09T09:00:00-05:00" // MUST be ISO 8601
}
```

**Response (Changes):**
```json
{
  "booking_id": 123,
  "status": "active",
  "timezone_id": "America/New_York", // <--- Returned here too
  "start_at": "2026-03-09T09:00:00-05:00",
  "start_at_utc": "2026-03-09T14:00:00Z"
}
```

### C. Error Codes
Handle these specific HTTP 4xx errors:

| Status Code | Error Key (detail) | Meaning | Action |
|:---:|:---|:---|:---|
| `409 Conflict` | `NO_PROVIDER_AVAILABLE` | The slot was taken while user was booking. | Show: "This slot is no longer available. Please choose another." |
| `400 Bad Request` | `INVALID_TIME` | The time does not exist (e.g., Spring-Forward gap). | Show: "This time is not valid due to Daylight Saving Time changes." |
| `400 Bad Request` | `SHOP_NOT_READY` | Shop hasn't migrated to new system. | Fallback to legacy flow (if supported) or error. |

---

## 3. Implementation Checklist for Flutter

### 1. Update Models
Update your `AvailabilityResponse` and `Slot` models to parse the new fields.

**Dart Example:**
```dart
class AvailabilitySlot {
  final DateTime startAt;    // Parsed from "start_at" (Preserves Offset)
  final DateTime startAtUtc; // Parsed from "start_at_utc"
  final int count;

  AvailabilitySlot.fromJson(Map<String, dynamic> json)
      : startAt = DateTime.parse(json['start_at']),
        startAtUtc = DateTime.parse(json['start_at_utc']),
        count = json['availability_count'];
}

class AvailabilityResponse {
  final String timezoneId;
  final List<AvailabilitySlot> slots;

  AvailabilityResponse.fromJson(Map<String, dynamic> json)
      : timezoneId = json['timezone_id'],
        slots = (json['available_slots'] as List)
            .map((s) => AvailabilitySlot.fromJson(s))
            .toList();
}
```

### 2. Timezone Display Logic
**CRITICAL:** Do **NOT** convert the time to the user's local phone time. You must display the time in the **Shop's Timezone**.

*   **Scenario:** User is in London (GMT), booking a haircut in New York (EST).
*   **Behavior:** App should show "9:00 AM" (New York time), NOT "2:00 PM" (London time).

**How to implement:**
1.  Use the `start_at` string from the API directly for display if possible (it contains the correct wall time `09:00`).
2.  Or use the `timezone_id` from the response ("America/New_York") to format the `start_at_utc` explicitly.
    *   *Recommended Package:* `timezone` (pub.dev)
    *   `TZDateTime.from(startAtUtc, getLocation(timezoneId))`

### 3. "Any Provider" Handling
If `provider_id` is null in the POST request:
- The backend runs a load-balancing algorithm.
- It assigns the best provider automatically.
- The response will contain the assigned `provider_id` and `provider_name`.

### 4. Conflict Handling
- Wrap the booking call in a try/catch.
- If `409 NO_PROVIDER_AVAILABLE` occurs, trigger a refresh of the availability grid automatically.

---

## 4. Best Practices

1.  **Always Send ISO 8601:** Verify your `start_at` in POST requests includes the timezone offset (e.g., `-05:00`).
2.  **Trust the Backend:** Don't try to calculate valid slots on the client. Only show what `GET /availability/` returns.
3.  **DST Awareness:** Be aware that on **March 8, 2026** (Spring Forward) and **Nov 1, 2026** (Fall Back), slot intervals might look irregular (e.g., jumping from 1:30 to 3:00). This is expected behavior.
