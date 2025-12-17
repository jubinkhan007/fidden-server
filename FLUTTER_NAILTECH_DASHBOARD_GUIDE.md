# Nail Tech Dashboard - Flutter Integration Guide

> **Backend:** Fully implemented on `phase2` branch (commit 094ac7f)
> **Endpoints Base URL:** `/api/nailtech/`

---

## 🎯 Dashboard Overview

The Nail Tech Dashboard provides:
1. Style Requests (client nail style ideas)
2. Look-book / Moodboard (portfolio)
3. Bookings by Style Type
4. Tip Summary
5. Aggregated Dashboard Metrics

---

## 🎨 UI Modification Guide (Figma → Spec)

### ✅ KEEP (In Spec & Has Backend)

| UI Element | Endpoint |
|------------|----------|
| Niche Chips | `/accounts/me/` → `primary_niche` |
| Upcoming Appointment | `/api/barber/today-appointments/` |
| Today's Schedule | `/api/barber/today-appointments/` |
| Today's Earnings | `/api/barber/daily-revenue/` |
| Style Requests | `/api/nailtech/style-requests/` |
| Look-book | `/api/nailtech/lookbook/` |
| Reviews | `/api/ratings/shop/{id}/` |

### ❌ REMOVE (Not in Spec)

| UI Element | Reason |
|------------|--------|
| Monthly Projection | Not in nail tech spec |
| Top Booked Services Count | Not in spec |
| Reschedule Counts | Not in spec |

### ➕ ADD (New Features)

| Feature | Endpoint |
|---------|----------|
| Bookings by Style | `/api/nailtech/bookings-by-style/` |
| Tip Summary | `/api/nailtech/tip-summary/` |
| Client Repeat Rate | `/api/nailtech/dashboard/` |

---

## 📱 Endpoints & Response Samples

### 1. Dashboard Summary
**GET** `/api/nailtech/dashboard/`

```json
{
  "today_appointments_count": 5,
  "today_revenue": 450.00,
  "pending_style_requests": 3,
  "repeat_customer_rate": 35.5,
  "weekly_tips": 120.00,
  "lookbook_count": 24
}
```

---

### 2. Style Requests

#### List Style Requests
**GET** `/api/nailtech/style-requests/`

```json
[
  {
    "id": 1,
    "shop": 1,
    "user": 42,
    "user_name": "Sarah Johnson",
    "user_email": "sarah@example.com",
    "booking": null,
    "title": "Floral Design",
    "description": "I want pink flowers on almond shaped nails",
    "nail_style_type": "gel",
    "nail_style_type_display": "Gel",
    "nail_shape": "almond",
    "nail_shape_display": "Almond",
    "color_preference": "Pink with white accents",
    "status": "pending",
    "images": [
      {
        "id": 1,
        "image": "https://storage.url/style_requests/ref1.jpg",
        "uploaded_at": "2025-12-15T10:00:00Z"
      }
    ],
    "created_at": "2025-12-15T10:00:00Z",
    "updated_at": "2025-12-15T10:00:00Z"
  }
]
```

#### Create Style Request (Client)
**POST** `/api/nailtech/style-requests/`

**Request (multipart/form-data):**
```
shop: 1
title: "Geometric Nail Art"
description: "Black and gold geometric patterns"
nail_style_type: "nail_art"
nail_shape: "coffin"
color_preference: "Black with gold foil"
images: [file1.jpg, file2.jpg]
```

#### Update Status (Owner)
**PATCH** `/api/nailtech/style-requests/{id}/`

```json
{
  "status": "approved"  // pending | approved | declined | completed
}
```

---

### 3. Look-book (Portfolio)
**GET** `/api/nailtech/lookbook/`

```json
{
  "count": 24,
  "items": [
    {
      "id": 1,
      "image": "https://storage.url/gallery/nail1.jpg",
      "thumbnail": "https://storage.url/gallery/thumb_nail1.jpg",
      "caption": "Floral Sleeve Concept",
      "category_tag": "nail_lookbook",
      "is_public": true,
      "created_at": "2025-12-10T14:00:00Z"
    }
  ]
}
```

---

### 4. Bookings by Style Type
**GET** `/api/nailtech/bookings-by-style/?days=30`

```json
{
  "period_days": 30,
  "styles": [
    {
      "style_type": "gel",
      "style_display": "Gel",
      "count": 45,
      "revenue": 2250.00
    },
    {
      "style_type": "acrylic",
      "style_display": "Acrylic",
      "count": 32,
      "revenue": 1920.00
    }
  ]
}
```

---

### 5. Tip Summary
**GET** `/api/nailtech/tip-summary/?period=week`

Query params: `period=day|week|month`

```json
{
  "period": "week",
  "total_tips": 120.00,
  "tip_count": 15,
  "average_tip": 8.00
}
```

---

## 🛠️ Flutter Implementation

### 1. Create Nail Tech Service

```dart
// lib/services/nailtech_dashboard_service.dart

class NailTechDashboardService {
  final Dio _dio;
  
  NailTechDashboardService(this._dio);
  
  // Dashboard Summary
  Future<NailTechDashboard> getDashboard() async {
    final response = await _dio.get('/api/nailtech/dashboard/');
    return NailTechDashboard.fromJson(response.data);
  }
  
  // Style Requests
  Future<List<StyleRequest>> getStyleRequests() async {
    final response = await _dio.get('/api/nailtech/style-requests/');
    return (response.data as List).map((e) => StyleRequest.fromJson(e)).toList();
  }
  
  Future<StyleRequest> createStyleRequest({
    required int shopId,
    required String title,
    required String description,
    String? nailStyleType,
    String? nailShape,
    String? colorPreference,
    List<File>? images,
  }) async {
    final formData = FormData.fromMap({
      'shop': shopId,
      'title': title,
      'description': description,
      if (nailStyleType != null) 'nail_style_type': nailStyleType,
      if (nailShape != null) 'nail_shape': nailShape,
      if (colorPreference != null) 'color_preference': colorPreference,
      if (images != null) 'images': images.map((f) => MultipartFile.fromFileSync(f.path)).toList(),
    });
    final response = await _dio.post('/api/nailtech/style-requests/', data: formData);
    return StyleRequest.fromJson(response.data);
  }
  
  Future<void> updateStyleRequestStatus(int id, String status) async {
    await _dio.patch('/api/nailtech/style-requests/$id/', data: {'status': status});
  }
  
  // Lookbook
  Future<LookbookResponse> getLookbook() async {
    final response = await _dio.get('/api/nailtech/lookbook/');
    return LookbookResponse.fromJson(response.data);
  }
  
  // Bookings by Style
  Future<BookingsByStyleResponse> getBookingsByStyle({int days = 30}) async {
    final response = await _dio.get('/api/nailtech/bookings-by-style/', queryParameters: {'days': days});
    return BookingsByStyleResponse.fromJson(response.data);
  }
  
  // Tip Summary
  Future<TipSummary> getTipSummary({String period = 'week'}) async {
    final response = await _dio.get('/api/nailtech/tip-summary/', queryParameters: {'period': period});
    return TipSummary.fromJson(response.data);
  }
}
```

### 2. Models

```dart
// lib/models/nailtech_dashboard.dart

enum NailStyleType { acrylic, gel, dip, natural, pedicure, nail_art }
enum NailShape { coffin, almond, stiletto, square, round, oval, squoval }
enum StyleRequestStatus { pending, approved, declined, completed }

class StyleRequest {
  final int id;
  final String userName;
  final String title;
  final String description;
  final NailStyleType? nailStyleType;
  final NailShape? nailShape;
  final String? colorPreference;
  final StyleRequestStatus status;
  final List<StyleRequestImage> images;
  final DateTime createdAt;
  
  // fromJson...
}

class NailTechDashboard {
  final int todayAppointmentsCount;
  final double todayRevenue;
  final int pendingStyleRequests;
  final double repeatCustomerRate;
  final double weeklyTips;
  final int lookbookCount;
  
  // fromJson...
}

class TipSummary {
  final String period;
  final double totalTips;
  final int tipCount;
  final double averageTip;
  
  // fromJson...
}
```

---

## 🔗 UI Component Mapping

| UI Element | Endpoint | Data Field |
|------------|----------|------------|
| Pending Style Requests Badge | `dashboard` | `pending_style_requests` |
| Today's Revenue | `dashboard` | `today_revenue` |
| Repeat Customer % | `dashboard` | `repeat_customer_rate` |
| Weekly Tips | `dashboard` | `weekly_tips` |
| Lookbook Count | `dashboard` | `lookbook_count` |
| Style Request List | `style-requests` | array |
| Lookbook Grid | `lookbook` | `items` |
| Style Type Chart | `bookings-by-style` | `styles` |

---

## ✅ Checklist

- [ ] Create `NailTechDashboardService`
- [ ] Create data models with enums
- [ ] Build `NailTechDashboardScreen`
- [ ] Implement Style Request list with approval actions
- [ ] Implement Lookbook grid (reuse GalleryItem UI)
- [ ] Add Style Type pie/bar chart
- [ ] Show tip summary card
