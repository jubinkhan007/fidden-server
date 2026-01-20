# Flutter Service Niche Integration Guide

This document explains the backend changes made to support niche-specific features in the Flutter app.

---

## Service Details Endpoint Update

### Endpoint: `GET /api/services/{service_id}/`

### New Field: `service_niche`

Returns the niche based on the **service's category** (not the shop's niche).

**Response Example:**
```json
{
  "id": 1,
  "title": "HairCut",
  "price": "100.00",
  "discount_price": "80.00",
  "shop_id": 1,
  "shop_name": "All-in-one Shop",
  "service_niche": "hairstylist",    // ← NEW FIELD
  "shop_address": "123 Main St",
  "shop_img": "https://...",
  "avg_rating": 4.5,
  "review_count": 10,
  "requires_age_18_plus": false,
  ...
}
```

---

## Category to Niche Mapping

| Service Category | `service_niche` Value |
|------------------|----------------------|
| Hair | `hairstylist` |
| Haircut | `hairstylist` |
| HairStyle | `hairstylist` |
| Nails | `nail_tech` |
| Skincare | `esthetician` |
| Massage | `massage_therapist` |
| Tattoo | `tattoo_artist` |
| Makeup | `makeup_artist` |
| Barber | `barber` |
| Other/Unknown | `general` |

---

## Flutter Usage

Use `service_niche` to determine which dashboard or UI to show:

```dart
// When user views a service detail
final serviceDetail = await api.get('/api/services/$serviceId/');
final serviceNiche = serviceDetail['service_niche'];

// Navigate to appropriate dashboard based on service niche
switch (serviceNiche) {
  case 'hairstylist':
    // Show hairstylist-specific features (hair profiles, consultations)
    break;
  case 'tattoo_artist':
    // Show tattoo-specific features (design gallery, consent forms)
    break;
  case 'nail_tech':
    // Show nail tech-specific features (nail styles, colors)
    break;
  case 'esthetician':
    // Show esthetician-specific features (skin analysis)
    break;
  case 'massage_therapist':
    // Show massage-specific features
    break;
  case 'makeup_artist':
    // Show makeup-specific features
    break;
  default:
    // Show general features
    break;
}
```

---

## Why `service_niche` Instead of `shop_niche`?

A shop can offer multiple services with different niches. For example:

| Shop | Service | service_niche |
|------|---------|---------------|
| All-in-one Shop | HairCut | `hairstylist` |
| All-in-one Shop | Tattoo | `tattoo_artist` |
| All-in-one Shop | Manicure | `nail_tech` |
| All-in-one Shop | Facial | `esthetician` |

The `service_niche` tells you the niche for **that specific service**, allowing the Flutter app to show niche-specific UI components regardless of what other services the shop offers.

---

## Related Endpoints

### Hairstylist Dashboard (Hair services only)

| Endpoint | Description |
|----------|-------------|
| `GET /api/hairstylist/dashboard/` | Filtered stats for hair services |
| `GET /api/hairstylist/weekly-schedule/?days=7` | Hair service appointments only |
| `GET /api/hairstylist/prep-notes/` | Today's hair appointments |

### Daily Revenue

| Endpoint | Description |
|----------|-------------|
| `GET /api/barber/daily-revenue/` | All services revenue |
| `GET /api/barber/daily-revenue/?niche=tattoo_artist` | Filtered by niche |

---

## Commits

| Commit | Description |
|--------|-------------|
| `f3d83df` | Added `service_niche` field to ServiceDetailSerializer |
| `e2ecfc0` | Fixed timezone handling for hairstylist dashboard |
| `13158a1` | Added category filtering to hairstylist dashboard |
