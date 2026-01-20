# Flutter Booking API Endpoints Guide

Complete reference for booking-related API endpoints with response structures.

---

## 1. Business Owner Bookings

### **Endpoint:** `GET /payments/bookings/?shop_id={shop_id}`

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `shop_id` | Yes | Shop ID (required for owners) |

**Response:**
```json
{
  "next": "https://api.example.com/payments/bookings/?cursor=abc123",
  "previous": null,
  "results": [
    {
      "id": 123,
      "user": 45,
      "user_email": "customer@example.com",
      "user_name": "John Doe",
      "profile_image": "https://api.example.com/media/profiles/user.jpg",
      "shop": 1,
      "shop_name": "Premium Cuts",
      "shop_niche": "barber",
      "slot": 789,
      "slot_time": "2026-01-03T14:00:00Z",
      "service_title": "Haircut",
      "service_duration": "30",
      "status": "active",
      "refund": null,
      "add_on_services": [
        {
          "title": "Beard Trim",
          "duration": "15"
        }
      ],
      "shop_timezone": "America/New_York",
      "created_at": "2026-01-01T10:00:00Z",
      "updated_at": "2026-01-01T10:00:00Z",
      "deposit_status": "held",
      "deposit_amount": "10.00",
      "service_price": "45.00",
      "remaining_amount": "35.00",
      "checkout_initiated": false,
      "prep_notes": "First-time customer, prefers shorter style"
    }
  ],
  "stats": {
    "total_bookings": 156,
    "new_bookings": 12,
    "cancelled": 5,
    "completed": 120
  }
}
```

**Status Values:**
- `active` - Upcoming/confirmed booking
- `completed` - Service completed
- `cancelled` - Customer cancelled
- `no-show` - Customer didn't show up
- `late-cancel` - Late cancellation

---

## 2. Today's Appointments (For Dashboard)

### **Endpoint:** `GET /api/barber/today-appointments/`

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `date` | No | Date filter (YYYY-MM-DD), defaults to today |
| `niche` | No | Filter by niche (see values below) |

**Niche Values:**
- `barber`, `tattoo`, `tattoo_artist`
- `esthetician`, `massage`, `massage_therapist`
- `hair`, `hairstylist`
- `nail`, `nail_tech`
- `makeup`, `makeup_artist`

**Response:**
```json
{
  "date": "2026-01-03",
  "count": 8,
  "niche": "barber",
  "stats": {
    "confirmed": 5,
    "completed": 2,
    "cancelled": 0,
    "no_show": 1
  },
  "appointments": [
    {
      "id": 123,
      "customer_name": "John Doe",
      "customer_phone": "555-1234",
      "customer_email": "john@example.com",
      "profile_image": "https://api.example.com/media/profiles/user.jpg",
      "service_title": "Haircut",
      "service_duration": 30,
      "start_time": "2026-01-03T09:00:00Z",
      "end_time": "2026-01-03T09:30:00Z",
      "status": "active",
      "is_walk_in": false,
      "add_on_services": [
        {
          "title": "Beard Trim",
          "duration": "15"
        }
      ],
      "deposit_status": "held",
      "deposit_amount": "10.00",
      "service_price": "35.00",
      "remaining_amount": "25.00",
      "prep_notes": "Prefers low fade"
    }
  ]
}
```

---

## 3. Customer Bookings

### **Endpoint:** `GET /payments/bookings/?user_email={email}`

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `user_email` | Yes | Customer's email address |
| `status` | No | Filter by status (comma-separated: `active,completed`) |
| `exclude_active` | No | Set to `true` to exclude active bookings |

**Response:**
```json
{
  "next": "https://api.example.com/payments/bookings/?cursor=xyz789",
  "previous": null,
  "results": [
    {
      "id": 123,
      "user": 45,
      "user_email": "john@example.com",
      "shop": 1,
      "shop_name": "Premium Cuts",
      "shop_address": "123 Main St, City, State 12345",
      "shop_img": "https://api.example.com/media/shops/shop1.jpg",
      "slot": 789,
      "slot_time": "2026-01-03T14:00:00Z",
      "service_id": "42",
      "service_title": "Haircut",
      "service_img": "https://api.example.com/media/services/haircut.jpg",
      "service_duration": "30",
      "status": "active",
      "created_at": "2026-01-01T10:00:00Z",
      "updated_at": "2026-01-01T10:00:00Z",
      "avg_rating": 4.8,
      "total_reviews": 156,
      "refund": null,
      "add_on_services": [
        {
          "title": "Beard Trim",
          "duration": "15"
        }
      ],
      "shop_timezone": "America/New_York",
      "deposit_status": "held",
      "deposit_amount": "10.00",
      "service_price": "45.00",
      "remaining_amount": "35.00",
      "checkout_initiated": false
    }
  ],
  "stats": {
    "total_bookings": 25,
    "new_bookings": 3,
    "cancelled": 2,
    "completed": 18
  }
}
```

---

## Summary Table

| Use Case | Endpoint | Required Param |
|----------|----------|----------------|
| Owner's all bookings | `GET /payments/bookings/` | `shop_id` |
| Today's appointments | `GET /api/barber/today-appointments/` | None (auto-detects shop) |
| Customer's bookings | `GET /payments/bookings/` | `user_email` |

---

## Common Fields Explained

| Field | Description |
|-------|-------------|
| `slot_time` | Booking start time in UTC (Z suffix) |
| `shop_timezone` | IANA timezone for local display |
| `deposit_status` | `held`, `credited`, or `forfeited` |
| `checkout_initiated` | Owner started checkout process |
| `is_walk_in` | True if walk-in (not pre-booked) |
| `prep_notes` | Owner's notes for appointment prep |
