# Hairstylist Dashboard - Latest Changes

## 1. Client Self-Service Hair Profile

**Endpoint:** `/api/my-hair-profile/`

**Who can use:** Logged-in **clients** (not owners)

| Method | Request | Response |
|--------|---------|----------|
| GET | `?shop_id=5` | `{exists: true/false, profile: {...}}` |
| POST | `{shop_id: 5, hair_type: "3c", ...}` | Created profile |
| PATCH | `{shop_id: 5, current_color: "Auburn"}` | Updated profile |

```dart
// API constant
static const String myHairProfile = '$_baseUrl/api/my-hair-profile/';

// Check if profile exists
final response = await dio.get('/api/my-hair-profile/', queryParameters: {'shop_id': shopId});
final exists = response.data['exists'];

// Create profile
await dio.post('/api/my-hair-profile/', data: {
  'shop_id': shopId,
  'hair_type': '3c',
  'hair_texture': 'medium',
});

// Update profile
await dio.patch('/api/my-hair-profile/', data: {
  'shop_id': shopId,
  'allergies': 'PPD sensitivity',
});
```

---

## 2. Owner Client Profile Endpoint

**Endpoint:** `/api/hairstylist/client-profiles/`

**Who can use:** Shop **owners** only

Owners can create/edit profiles for ANY client who has booked with them.

```dart
// Create profile for a client (owner flow)
await dio.post('/api/hairstylist/client-profiles/', data: {
  'client': 42,  // client user ID
  'hair_type': '4a',
  'allergies': 'None',
});
```

---

## 3. Booking Response Enhancements

New fields added to `ownerBookingSerializer`:

```dart
class Booking {
  // ... existing fields ...
  
  final String? prepNotes;    // NEW: Stylist prep notes
  final String? shopNiche;    // NEW: "hairstylist", "barber", etc.
}

// Parse from JSON
prepNotes = json['prep_notes'] ?? '';
shopNiche = json['shop_niche'];
```

**Usage in Flutter:**
```dart
// Conditionally show prep notes based on niche
if (booking.shopNiche == 'hairstylist') {
  TextField(
    initialValue: booking.prepNotes,
    onChanged: (value) => updatePrepNotes(booking.id, value),
  );
}
```

---

## Summary

| Feature | Endpoint | User |
|---------|----------|------|
| Client self-service profile | `GET/POST/PATCH /api/my-hair-profile/` | Client |
| Owner manages profiles | `CRUD /api/hairstylist/client-profiles/` | Owner |
| Prep notes in booking | `booking.prep_notes` field | Owner |
| Shop niche in booking | `booking.shop_niche` field | Both |
