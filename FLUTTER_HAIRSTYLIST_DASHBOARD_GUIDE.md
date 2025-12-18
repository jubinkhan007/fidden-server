# Flutter Hairstylist/Loctician Dashboard Integration Guide

## Overview

This guide covers the Flutter implementation for the Hairstylist/Loctician niche dashboard. The backend reuses existing infrastructure (appointments, revenue, portfolio) and adds hairstylist-specific features (Client Hair Profiles, Weekly Schedule, Prep Notes, Product Recommendations).

---

## API Constants

Add to `lib/core/constants/api_constants.dart`:

```dart
// ==========================================
// Hairstylist Dashboard Endpoints 💇‍♀️
// ==========================================
static const String hairstylistDashboard = '$_baseUrl/api/hairstylist/dashboard/';
static const String hairstylistWeeklySchedule = '$_baseUrl/api/hairstylist/weekly-schedule/';
static const String hairstylistPrepNotes = '$_baseUrl/api/hairstylist/prep-notes/';
static const String hairstylistClientProfiles = '$_baseUrl/api/hairstylist/client-profiles/';
static String hairstylistClientProfileDetail(int id) => '$_baseUrl/api/hairstylist/client-profiles/$id/';
static const String hairstylistRecommendations = '$_baseUrl/api/hairstylist/recommendations/';
static String hairstylistRecommendationDetail(int id) => '$_baseUrl/api/hairstylist/recommendations/$id/';

// Reused from Barber (no changes needed)
// static const String todayAppointments = '$_baseUrl/api/barber/today-appointments/';
// static const String dailyRevenue = '$_baseUrl/api/barber/daily-revenue/';
```

---

## Data Models

### `lib/features/business_owner/hairstylist/data/hairstylist_models.dart`

```dart
// ==========================================
// ENUMS
// ==========================================

enum HairType {
  type1a('1a', '1A - Fine Straight'),
  type1b('1b', '1B - Medium Straight'),
  type1c('1c', '1C - Coarse Straight'),
  type2a('2a', '2A - Fine Wavy'),
  type2b('2b', '2B - Medium Wavy'),
  type2c('2c', '2C - Coarse Wavy'),
  type3a('3a', '3A - Loose Curls'),
  type3b('3b', '3B - Springy Curls'),
  type3c('3c', '3C - Tight Curls'),
  type4a('4a', '4A - Soft Coils'),
  type4b('4b', '4B - Z-Pattern Coils'),
  type4c('4c', '4C - Tight Coils');

  final String value;
  final String display;
  const HairType(this.value, this.display);

  static HairType? fromString(String? value) {
    if (value == null || value.isEmpty) return null;
    return HairType.values.firstWhere((e) => e.value == value, orElse: () => HairType.type3a);
  }
}

enum HairTexture {
  fine('fine', 'Fine'),
  medium('medium', 'Medium'),
  coarse('coarse', 'Coarse');

  final String value;
  final String display;
  const HairTexture(this.value, this.display);
}

enum HairPorosity {
  low('low', 'Low'),
  normal('normal', 'Normal'),
  high('high', 'High');

  final String value;
  final String display;
  const HairPorosity(this.value, this.display);
}

enum ProductCategory {
  shampoo('shampoo', 'Shampoo'),
  conditioner('conditioner', 'Conditioner'),
  treatment('treatment', 'Treatment'),
  oil('oil', 'Oil'),
  styling('styling', 'Styling Product'),
  protectant('protectant', 'Heat Protectant'),
  leaveIn('leave_in', 'Leave-In'),
  mask('mask', 'Hair Mask'),
  color('color', 'Color Product'),
  tool('tool', 'Tool/Accessory'),
  other('other', 'Other');

  final String value;
  final String display;
  const ProductCategory(this.value, this.display);

  static ProductCategory fromString(String? value) {
    return ProductCategory.values.firstWhere(
      (e) => e.value == value,
      orElse: () => ProductCategory.other,
    );
  }
}

// ==========================================
// MODELS
// ==========================================

class HairstylistDashboard {
  final int todayAppointmentsCount;
  final int weekAppointmentsCount;
  final double todayRevenue;
  final int clientProfilesCount;
  final int productRecommendationsCount;
  final int consultationServicesCount;

  HairstylistDashboard({
    required this.todayAppointmentsCount,
    required this.weekAppointmentsCount,
    required this.todayRevenue,
    required this.clientProfilesCount,
    required this.productRecommendationsCount,
    required this.consultationServicesCount,
  });

  factory HairstylistDashboard.fromJson(Map<String, dynamic> json) {
    return HairstylistDashboard(
      todayAppointmentsCount: json['today_appointments_count'] ?? 0,
      weekAppointmentsCount: json['week_appointments_count'] ?? 0,
      todayRevenue: (json['today_revenue'] ?? 0).toDouble(),
      clientProfilesCount: json['client_profiles_count'] ?? 0,
      productRecommendationsCount: json['product_recommendations_count'] ?? 0,
      consultationServicesCount: json['consultation_services_count'] ?? 0,
    );
  }
}

class ClientHairProfile {
  final int id;
  final int shopId;
  final int clientId;
  final String? clientName;
  final String? clientEmail;
  final String? hairType;
  final String? hairTypeDisplay;
  final String? hairTexture;
  final String? hairTextureDisplay;
  final String? hairPorosity;
  final String? hairPorosityDisplay;
  final String? naturalColor;
  final String? currentColor;
  final String? colorHistory;
  final String? chemicalHistory;
  final String? scalpCondition;
  final String? allergies;
  final String? preferences;
  final DateTime createdAt;
  final DateTime updatedAt;

  ClientHairProfile({
    required this.id,
    required this.shopId,
    required this.clientId,
    this.clientName,
    this.clientEmail,
    this.hairType,
    this.hairTypeDisplay,
    this.hairTexture,
    this.hairTextureDisplay,
    this.hairPorosity,
    this.hairPorosityDisplay,
    this.naturalColor,
    this.currentColor,
    this.colorHistory,
    this.chemicalHistory,
    this.scalpCondition,
    this.allergies,
    this.preferences,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ClientHairProfile.fromJson(Map<String, dynamic> json) {
    return ClientHairProfile(
      id: json['id'],
      shopId: json['shop'],
      clientId: json['client'],
      clientName: json['client_name'],
      clientEmail: json['client_email'],
      hairType: json['hair_type'],
      hairTypeDisplay: json['hair_type_display'],
      hairTexture: json['hair_texture'],
      hairTextureDisplay: json['hair_texture_display'],
      hairPorosity: json['hair_porosity'],
      hairPorosityDisplay: json['hair_porosity_display'],
      naturalColor: json['natural_color'],
      currentColor: json['current_color'],
      colorHistory: json['color_history'],
      chemicalHistory: json['chemical_history'],
      scalpCondition: json['scalp_condition'],
      allergies: json['allergies'],
      preferences: json['preferences'],
      createdAt: DateTime.parse(json['created_at']),
      updatedAt: DateTime.parse(json['updated_at']),
    );
  }

  Map<String, dynamic> toJson() => {
    'client': clientId,
    'hair_type': hairType,
    'hair_texture': hairTexture,
    'hair_porosity': hairPorosity,
    'natural_color': naturalColor,
    'current_color': currentColor,
    'color_history': colorHistory,
    'chemical_history': chemicalHistory,
    'scalp_condition': scalpCondition,
    'allergies': allergies,
    'preferences': preferences,
  };
}

class ProductRecommendation {
  final int id;
  final int shopId;
  final int clientId;
  final String? clientName;
  final int? bookingId;
  final String productName;
  final String? brand;
  final String category;
  final String? categoryDisplay;
  final String? notes;
  final String? purchaseLink;
  final DateTime createdAt;

  ProductRecommendation({
    required this.id,
    required this.shopId,
    required this.clientId,
    this.clientName,
    this.bookingId,
    required this.productName,
    this.brand,
    required this.category,
    this.categoryDisplay,
    this.notes,
    this.purchaseLink,
    required this.createdAt,
  });

  factory ProductRecommendation.fromJson(Map<String, dynamic> json) {
    return ProductRecommendation(
      id: json['id'],
      shopId: json['shop'],
      clientId: json['client'],
      clientName: json['client_name'],
      bookingId: json['booking'],
      productName: json['product_name'] ?? '',
      brand: json['brand'],
      category: json['category'] ?? 'other',
      categoryDisplay: json['category_display'],
      notes: json['notes'],
      purchaseLink: json['purchase_link'],
      createdAt: DateTime.parse(json['created_at']),
    );
  }

  Map<String, dynamic> toJson() => {
    'client': clientId,
    'booking': bookingId,
    'product_name': productName,
    'brand': brand,
    'category': category,
    'notes': notes,
    'purchase_link': purchaseLink,
  };
}

class PrepNoteItem {
  final int id;
  final String userName;
  final String serviceTitle;
  final DateTime slotTime;
  final String prepNotes;
  final String status;

  PrepNoteItem({
    required this.id,
    required this.userName,
    required this.serviceTitle,
    required this.slotTime,
    required this.prepNotes,
    required this.status,
  });

  factory PrepNoteItem.fromJson(Map<String, dynamic> json) {
    return PrepNoteItem(
      id: json['id'],
      userName: json['user_name'] ?? '',
      serviceTitle: json['service_title'] ?? '',
      slotTime: DateTime.parse(json['slot_time']),
      prepNotes: json['prep_notes'] ?? '',
      status: json['status'] ?? 'active',
    );
  }
}
```

---

## API Endpoints & Responses

### 1. Dashboard Summary

**GET** `/api/hairstylist/dashboard/`

```json
{
  "today_appointments_count": 5,
  "week_appointments_count": 18,
  "today_revenue": 450.00,
  "client_profiles_count": 32,
  "product_recommendations_count": 45,
  "consultation_services_count": 3
}
```

---

### 2. Weekly Schedule

**GET** `/api/hairstylist/weekly-schedule/?days=7`

```json
{
  "start_date": "2025-12-18",
  "end_date": "2025-12-25",
  "total_appointments": 18,
  "schedule": {
    "2025-12-18": [
      {
        "id": 1,
        "user_name": "Sarah Johnson",
        "user_email": "sarah@email.com",
        "service_title": "Color & Style",
        "slot_time": "2025-12-18T10:00:00Z",
        "status": "active",
        "prep_notes": "Bring gloves, client wants balayage"
      }
    ],
    "2025-12-19": []
  }
}
```

---

### 3. Prep Notes

**GET** `/api/hairstylist/prep-notes/`
```json
{
  "count": 3,
  "appointments": [
    {
      "id": 1,
      "user_name": "Sarah Johnson",
      "service_title": "Color & Style",
      "slot_time": "2025-12-18T10:00:00Z",
      "prep_notes": "Client wants balayage, bring developer",
      "status": "active"
    }
  ]
}
```

**PATCH** `/api/hairstylist/prep-notes/`
```json
{
  "booking_id": 1,
  "prep_notes": "Client wants balayage, bring developer and gloves"
}
```

---

### 4. Client Hair Profiles

**GET** `/api/hairstylist/client-profiles/`

```json
[
  {
    "id": 1,
    "shop": 5,
    "client": 42,
    "client_name": "Sarah Johnson",
    "client_email": "sarah@email.com",
    "hair_type": "3c",
    "hair_type_display": "3C - Tight Curls",
    "hair_texture": "medium",
    "hair_texture_display": "Medium",
    "hair_porosity": "high",
    "hair_porosity_display": "High",
    "natural_color": "Black",
    "current_color": "Auburn",
    "color_history": "Box dye 2023, salon highlights 2024",
    "chemical_history": "No relaxers, keratin treatment 2024",
    "scalp_condition": "Slightly dry",
    "allergies": "PPD sensitivity",
    "preferences": "Prefers gentle products, no sulfates",
    "created_at": "2025-12-10T14:00:00Z",
    "updated_at": "2025-12-15T09:30:00Z"
  }
]
```

**POST** `/api/hairstylist/client-profiles/`
```json
{
  "client": 42,
  "hair_type": "3c",
  "hair_texture": "medium",
  "hair_porosity": "high",
  "natural_color": "Black",
  "current_color": "Auburn",
  "color_history": "Box dye 2023",
  "allergies": "PPD sensitivity"
}
```

---

### 5. Product Recommendations

**GET** `/api/hairstylist/recommendations/?client=42`

```json
[
  {
    "id": 1,
    "shop": 5,
    "client": 42,
    "client_name": "Sarah Johnson",
    "booking": 123,
    "product_name": "Olaplex No. 3",
    "brand": "Olaplex",
    "category": "treatment",
    "category_display": "Treatment",
    "notes": "Use weekly for bond repair",
    "purchase_link": "https://www.olaplex.com",
    "created_at": "2025-12-15T10:00:00Z"
  }
]
```

**POST** `/api/hairstylist/recommendations/`
```json
{
  "client": 42,
  "booking": 123,
  "product_name": "Olaplex No. 3",
  "brand": "Olaplex",
  "category": "treatment",
  "notes": "Use weekly for bond repair",
  "purchase_link": "https://www.olaplex.com"
}
```

---

## Reused Endpoints (No Changes)

| Feature | Endpoint | Notes |
|---------|----------|-------|
| Today's Appointments | `GET /api/barber/today-appointments/` | Already exists |
| Daily Revenue | `GET /api/barber/daily-revenue/` | Already exists |
| Portfolio | `GET /api/portfolio/?niche=hair` | Tag-based filtering |
| Reviews | `GET /api/ratings/shop/{shop_id}/` | Already exists |

---

## Service Layer

### `lib/features/business_owner/hairstylist/services/hairstylist_service.dart`

```dart
class HairstylistService {
  final Dio _dio;
  HairstylistService(this._dio);

  Future<HairstylistDashboard> getDashboard() async {
    final response = await _dio.get('/api/hairstylist/dashboard/');
    return HairstylistDashboard.fromJson(response.data);
  }

  Future<Map<String, List<PrepNoteItem>>> getWeeklySchedule({int days = 7}) async {
    final response = await _dio.get('/api/hairstylist/weekly-schedule/', 
      queryParameters: {'days': days});
    final schedule = <String, List<PrepNoteItem>>{};
    (response.data['schedule'] as Map).forEach((date, appointments) {
      schedule[date] = (appointments as List)
          .map((e) => PrepNoteItem.fromJson(e)).toList();
    });
    return schedule;
  }

  Future<List<PrepNoteItem>> getPrepNotes() async {
    final response = await _dio.get('/api/hairstylist/prep-notes/');
    return (response.data['appointments'] as List)
        .map((e) => PrepNoteItem.fromJson(e)).toList();
  }

  Future<void> updatePrepNotes(int bookingId, String notes) async {
    await _dio.patch('/api/hairstylist/prep-notes/', 
      data: {'booking_id': bookingId, 'prep_notes': notes});
  }

  Future<List<ClientHairProfile>> getClientProfiles() async {
    final response = await _dio.get('/api/hairstylist/client-profiles/');
    return (response.data as List)
        .map((e) => ClientHairProfile.fromJson(e)).toList();
  }

  Future<ClientHairProfile> createClientProfile(ClientHairProfile profile) async {
    final response = await _dio.post('/api/hairstylist/client-profiles/', 
      data: profile.toJson());
    return ClientHairProfile.fromJson(response.data);
  }

  Future<List<ProductRecommendation>> getRecommendations({int? clientId}) async {
    final response = await _dio.get('/api/hairstylist/recommendations/',
      queryParameters: clientId != null ? {'client': clientId} : null);
    return (response.data as List)
        .map((e) => ProductRecommendation.fromJson(e)).toList();
  }

  Future<ProductRecommendation> createRecommendation(ProductRecommendation rec) async {
    final response = await _dio.post('/api/hairstylist/recommendations/', 
      data: rec.toJson());
    return ProductRecommendation.fromJson(response.data);
  }
}
```

---

## File Structure

```
lib/features/business_owner/hairstylist/
├── data/
│   └── hairstylist_models.dart
├── services/
│   └── hairstylist_service.dart
├── controllers/
│   ├── hairstylist_dashboard_controller.dart
│   ├── client_hair_profile_controller.dart
│   └── product_recommendation_controller.dart
└── presentation/
    ├── widgets/
    │   ├── hairstylist_dashboard_content.dart
    │   ├── weekly_schedule_widget.dart
    │   ├── prep_notes_card.dart
    │   ├── hair_profile_card.dart
    │   └── product_recommendation_tile.dart
    └── screens/
        ├── weekly_schedule_screen.dart
        ├── client_hair_profiles_screen.dart
        ├── hair_profile_detail_screen.dart
        └── product_recommendations_screen.dart
```

---

## Summary

| Feature | Backend Status | Flutter Action |
|---------|----------------|----------------|
| Dashboard metrics | ✅ Ready | Build `HairstylistDashboardContent` |
| Weekly schedule | ✅ Ready | Build calendar/list view |
| Prep notes | ✅ Ready | Build editable card |
| Client hair profiles | ✅ Ready | Build profile list/detail |
| Product recommendations | ✅ Ready | Build recommendation list |
| Appointments | ✅ Reuse barber | No changes |
| Revenue | ✅ Reuse barber | No changes |
| Portfolio | ✅ Use `?niche=hair` | No changes |
| Reviews | ✅ Reuse existing | No changes |
