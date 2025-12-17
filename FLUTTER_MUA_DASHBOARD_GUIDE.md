# Flutter Makeup Artist (MUA) Dashboard Integration Guide

## Overview

This guide covers the Flutter implementation for the Makeup Artist niche dashboard. The backend reuses existing infrastructure (appointments, revenue, reviews) and adds MUA-specific features (Face Charts, Client Beauty Profiles, Product Kit).

---

## API Constants

Add to `lib/core/constants/api_constants.dart`:

```dart
// ==========================================
// MUA Dashboard Endpoints 💄
// ==========================================
static const String muaDashboard = '$_baseUrl/api/mua/dashboard/';
static const String muaFaceCharts = '$_baseUrl/api/mua/face-charts/';
static const String muaClientProfiles = '$_baseUrl/api/mua/client-profiles/';
static String muaClientProfileDetail(int id) => '$_baseUrl/api/mua/client-profiles/$id/';
static const String muaProductKit = '$_baseUrl/api/mua/product-kit/';
static String muaProductKitDetail(int id) => '$_baseUrl/api/mua/product-kit/$id/';

// Reused from Barber (no changes needed)
// static const String todayAppointments = '$_baseUrl/api/barber/today-appointments/';
// static const String dailyRevenue = '$_baseUrl/api/barber/daily-revenue/';
```

---

## Data Models

### `lib/features/business_owner/mua/data/mua_models.dart`

```dart
// ==========================================
// ENUMS
// ==========================================

enum LookType {
  natural('natural', 'Natural'),
  glam('glam', 'Glam'),
  bridal('bridal', 'Bridal'),
  editorial('editorial', 'Editorial'),
  sfx('sfx', 'Special Effects');

  final String value;
  final String display;
  const LookType(this.value, this.display);

  static LookType? fromString(String? value) {
    if (value == null || value.isEmpty) return null;
    return LookType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => LookType.natural,
    );
  }
}

enum SkinTone {
  fair('fair', 'Fair'),
  light('light', 'Light'),
  medium('medium', 'Medium'),
  olive('olive', 'Olive'),
  tan('tan', 'Tan'),
  deep('deep', 'Deep');

  final String value;
  final String display;
  const SkinTone(this.value, this.display);

  static SkinTone? fromString(String? value) {
    if (value == null || value.isEmpty) return null;
    return SkinTone.values.firstWhere(
      (e) => e.value == value,
      orElse: () => SkinTone.medium,
    );
  }
}

enum SkinType {
  normal('normal', 'Normal'),
  oily('oily', 'Oily'),
  dry('dry', 'Dry'),
  combination('combination', 'Combination'),
  sensitive('sensitive', 'Sensitive');

  final String value;
  final String display;
  const SkinType(this.value, this.display);

  static SkinType? fromString(String? value) {
    if (value == null || value.isEmpty) return null;
    return SkinType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => SkinType.normal,
    );
  }
}

enum Undertone {
  warm('warm', 'Warm'),
  cool('cool', 'Cool'),
  neutral('neutral', 'Neutral');

  final String value;
  final String display;
  const Undertone(this.value, this.display);
}

enum ProductCategory {
  foundation('foundation', 'Foundation'),
  concealer('concealer', 'Concealer'),
  powder('powder', 'Powder'),
  blush('blush', 'Blush'),
  bronzer('bronzer', 'Bronzer'),
  highlighter('highlighter', 'Highlighter'),
  eyeshadow('eyeshadow', 'Eyeshadow'),
  eyeliner('eyeliner', 'Eyeliner'),
  mascara('mascara', 'Mascara'),
  brow('brow', 'Brow Products'),
  lipstick('lipstick', 'Lipstick'),
  lipGloss('lip_gloss', 'Lip Gloss'),
  primer('primer', 'Primer'),
  settingSpray('setting_spray', 'Setting Spray'),
  brush('brush', 'Brush'),
  sponge('sponge', 'Sponge/Applicator'),
  skincare('skincare', 'Skincare'),
  other('other', 'Other');

  final String value;
  final String display;
  const ProductCategory(this.value, this.display);

  static ProductCategory fromString(String? value) {
    if (value == null) return ProductCategory.other;
    return ProductCategory.values.firstWhere(
      (e) => e.value == value,
      orElse: () => ProductCategory.other,
    );
  }
}

// ==========================================
// MODELS
// ==========================================

class MUADashboard {
  final int todayAppointmentsCount;
  final double todayRevenue;
  final int clientProfilesCount;
  final int productKitCount;
  final int faceChartsCount;
  final int mobileServicesCount;

  MUADashboard({
    required this.todayAppointmentsCount,
    required this.todayRevenue,
    required this.clientProfilesCount,
    required this.productKitCount,
    required this.faceChartsCount,
    required this.mobileServicesCount,
  });

  factory MUADashboard.fromJson(Map<String, dynamic> json) {
    return MUADashboard(
      todayAppointmentsCount: json['today_appointments_count'] ?? 0,
      todayRevenue: (json['today_revenue'] ?? 0).toDouble(),
      clientProfilesCount: json['client_profiles_count'] ?? 0,
      productKitCount: json['product_kit_count'] ?? 0,
      faceChartsCount: json['face_charts_count'] ?? 0,
      mobileServicesCount: json['mobile_services_count'] ?? 0,
    );
  }
}

class FaceChart {
  final int id;
  final int shopId;
  final String imageUrl;
  final String? thumbnailUrl;
  final String? caption;
  final String? description;
  final int? clientId;
  final String? clientName;
  final String? lookType;
  final String? categoryTag;
  final List<String> tags;
  final bool isPublic;
  final DateTime createdAt;

  FaceChart({
    required this.id,
    required this.shopId,
    required this.imageUrl,
    this.thumbnailUrl,
    this.caption,
    this.description,
    this.clientId,
    this.clientName,
    this.lookType,
    this.categoryTag,
    this.tags = const [],
    this.isPublic = true,
    required this.createdAt,
  });

  factory FaceChart.fromJson(Map<String, dynamic> json) {
    return FaceChart(
      id: json['id'],
      shopId: json['shop'],
      imageUrl: json['image'] ?? '',
      thumbnailUrl: json['thumbnail'],
      caption: json['caption'],
      description: json['description'],
      clientId: json['client'],
      clientName: json['client_name'],
      lookType: json['look_type'],
      categoryTag: json['category_tag'],
      tags: List<String>.from(json['tags'] ?? []),
      isPublic: json['is_public'] ?? true,
      createdAt: DateTime.parse(json['created_at']),
    );
  }

  LookType? get lookTypeEnum => LookType.fromString(lookType);
}

class ClientBeautyProfile {
  final int id;
  final int shopId;
  final int clientId;
  final String? clientName;
  final String? clientEmail;
  final String? skinTone;
  final String? skinToneDisplay;
  final String? skinType;
  final String? skinTypeDisplay;
  final String? undertone;
  final String? undertoneDisplay;
  final String? allergies;
  final String? preferences;
  final String? foundationShade;
  final DateTime createdAt;
  final DateTime updatedAt;

  ClientBeautyProfile({
    required this.id,
    required this.shopId,
    required this.clientId,
    this.clientName,
    this.clientEmail,
    this.skinTone,
    this.skinToneDisplay,
    this.skinType,
    this.skinTypeDisplay,
    this.undertone,
    this.undertoneDisplay,
    this.allergies,
    this.preferences,
    this.foundationShade,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ClientBeautyProfile.fromJson(Map<String, dynamic> json) {
    return ClientBeautyProfile(
      id: json['id'],
      shopId: json['shop'],
      clientId: json['client'],
      clientName: json['client_name'],
      clientEmail: json['client_email'],
      skinTone: json['skin_tone'],
      skinToneDisplay: json['skin_tone_display'],
      skinType: json['skin_type'],
      skinTypeDisplay: json['skin_type_display'],
      undertone: json['undertone'],
      undertoneDisplay: json['undertone_display'],
      allergies: json['allergies'],
      preferences: json['preferences'],
      foundationShade: json['foundation_shade'],
      createdAt: DateTime.parse(json['created_at']),
      updatedAt: DateTime.parse(json['updated_at']),
    );
  }

  Map<String, dynamic> toJson() => {
    'client': clientId,
    'skin_tone': skinTone,
    'skin_type': skinType,
    'undertone': undertone,
    'allergies': allergies,
    'preferences': preferences,
    'foundation_shade': foundationShade,
  };
}

class ProductKitItem {
  final int id;
  final int shopId;
  final String name;
  final String? brand;
  final String category;
  final String? categoryDisplay;
  final int quantity;
  final bool isPacked;
  final String? notes;
  final DateTime createdAt;

  ProductKitItem({
    required this.id,
    required this.shopId,
    required this.name,
    this.brand,
    required this.category,
    this.categoryDisplay,
    this.quantity = 1,
    this.isPacked = false,
    this.notes,
    required this.createdAt,
  });

  factory ProductKitItem.fromJson(Map<String, dynamic> json) {
    return ProductKitItem(
      id: json['id'],
      shopId: json['shop'],
      name: json['name'] ?? '',
      brand: json['brand'],
      category: json['category'] ?? 'other',
      categoryDisplay: json['category_display'],
      quantity: json['quantity'] ?? 1,
      isPacked: json['is_packed'] ?? false,
      notes: json['notes'],
      createdAt: DateTime.parse(json['created_at']),
    );
  }

  Map<String, dynamic> toJson() => {
    'name': name,
    'brand': brand,
    'category': category,
    'quantity': quantity,
    'is_packed': isPacked,
    'notes': notes,
  };

  ProductKitItem copyWith({bool? isPacked}) {
    return ProductKitItem(
      id: id,
      shopId: shopId,
      name: name,
      brand: brand,
      category: category,
      categoryDisplay: categoryDisplay,
      quantity: quantity,
      isPacked: isPacked ?? this.isPacked,
      notes: notes,
      createdAt: createdAt,
    );
  }
}
```

---

## API Endpoints & Responses

### 1. MUA Dashboard Summary

**GET** `/api/mua/dashboard/`

```json
{
  "today_appointments_count": 5,
  "today_revenue": 450.00,
  "client_profiles_count": 23,
  "product_kit_count": 48,
  "face_charts_count": 12,
  "mobile_services_count": 3
}
```

---

### 2. Face Charts (Reuses GalleryItem)

**GET** `/api/mua/face-charts/`
**Query Params:** `?look_type=bridal` (optional filter)

```json
{
  "count": 12,
  "items": [
    {
      "id": 1,
      "shop": 5,
      "image": "https://backend.fidden.io/media/gallery/face1.jpg",
      "thumbnail": "https://backend.fidden.io/media/gallery/thumbnails/face1.jpg",
      "caption": "Bridal Look - Sarah",
      "description": "Soft glam bridal makeup with champagne tones",
      "client": 42,
      "client_name": "Sarah Johnson",
      "look_type": "bridal",
      "category_tag": "face_chart",
      "tags": ["bridal", "glam", "champagne"],
      "is_public": false,
      "created_at": "2025-12-17T10:30:00Z"
    }
  ]
}
```

**POST** `/api/mua/face-charts/` (multipart/form-data)
```
image: <file>
caption: "Bridal Look - Sarah"
description: "Soft glam bridal makeup"
client: 42
look_type: "bridal"
```

---

### 3. Client Beauty Profiles

**GET** `/api/mua/client-profiles/`

```json
[
  {
    "id": 1,
    "shop": 5,
    "client": 42,
    "client_name": "Sarah Johnson",
    "client_email": "sarah@email.com",
    "skin_tone": "medium",
    "skin_tone_display": "Medium",
    "skin_type": "combination",
    "skin_type_display": "Combination",
    "undertone": "warm",
    "undertone_display": "Warm",
    "allergies": "Fragrance sensitivity",
    "preferences": "Prefers matte finish, no glitter",
    "foundation_shade": "MAC NC35",
    "created_at": "2025-12-10T14:00:00Z",
    "updated_at": "2025-12-15T09:30:00Z"
  }
]
```

**POST** `/api/mua/client-profiles/`
```json
{
  "client": 42,
  "skin_tone": "medium",
  "skin_type": "combination",
  "undertone": "warm",
  "allergies": "Fragrance sensitivity",
  "preferences": "Prefers matte finish",
  "foundation_shade": "MAC NC35"
}
```

**PATCH** `/api/mua/client-profiles/{id}/`
```json
{
  "foundation_shade": "MAC NC37"
}
```

---

### 4. Product Kit Checklist

**GET** `/api/mua/product-kit/`
**Query Params:** `?category=foundation` (optional filter)

```json
[
  {
    "id": 1,
    "shop": 5,
    "name": "Pro Longwear Foundation",
    "brand": "MAC",
    "category": "foundation",
    "category_display": "Foundation",
    "quantity": 2,
    "is_packed": true,
    "notes": "Shades NC25, NC35",
    "created_at": "2025-12-01T10:00:00Z"
  },
  {
    "id": 2,
    "shop": 5,
    "name": "Setting Spray",
    "brand": "Urban Decay",
    "category": "setting_spray",
    "category_display": "Setting Spray",
    "quantity": 1,
    "is_packed": false,
    "notes": "",
    "created_at": "2025-12-01T10:05:00Z"
  }
]
```

**POST** `/api/mua/product-kit/`
```json
{
  "name": "Pro Longwear Foundation",
  "brand": "MAC",
  "category": "foundation",
  "quantity": 2,
  "notes": "Shades NC25, NC35"
}
```

**PATCH** `/api/mua/product-kit/{id}/` (Toggle packed)
```json
{
  "is_packed": true
}
```

---

### 5. Reused Endpoints (No Changes)

| Feature | Endpoint | Notes |
|---------|----------|-------|
| Today's Appointments | `GET /api/barber/today-appointments/` | Already exists |
| Daily Revenue | `GET /api/barber/daily-revenue/` | Already exists |
| Reviews | `GET /api/ratings/shop/{shop_id}/` | Already exists |

---

## Service Layer

### `lib/features/business_owner/mua/services/mua_service.dart`

```dart
import 'package:dio/dio.dart';
import '../data/mua_models.dart';

class MUAService {
  final Dio _dio;

  MUAService(this._dio);

  // Dashboard Summary
  Future<MUADashboard> getDashboard() async {
    final response = await _dio.get('/api/mua/dashboard/');
    return MUADashboard.fromJson(response.data);
  }

  // Face Charts
  Future<List<FaceChart>> getFaceCharts({String? lookType}) async {
    final response = await _dio.get(
      '/api/mua/face-charts/',
      queryParameters: lookType != null ? {'look_type': lookType} : null,
    );
    return (response.data['items'] as List)
        .map((e) => FaceChart.fromJson(e))
        .toList();
  }

  Future<FaceChart> createFaceChart({
    required File image,
    String? caption,
    String? description,
    int? clientId,
    String? lookType,
  }) async {
    final formData = FormData.fromMap({
      'image': await MultipartFile.fromFile(image.path),
      if (caption != null) 'caption': caption,
      if (description != null) 'description': description,
      if (clientId != null) 'client': clientId,
      if (lookType != null) 'look_type': lookType,
    });
    final response = await _dio.post('/api/mua/face-charts/', data: formData);
    return FaceChart.fromJson(response.data);
  }

  // Client Beauty Profiles
  Future<List<ClientBeautyProfile>> getClientProfiles() async {
    final response = await _dio.get('/api/mua/client-profiles/');
    return (response.data as List)
        .map((e) => ClientBeautyProfile.fromJson(e))
        .toList();
  }

  Future<ClientBeautyProfile> createClientProfile(ClientBeautyProfile profile) async {
    final response = await _dio.post(
      '/api/mua/client-profiles/',
      data: profile.toJson(),
    );
    return ClientBeautyProfile.fromJson(response.data);
  }

  Future<ClientBeautyProfile> updateClientProfile(int id, Map<String, dynamic> updates) async {
    final response = await _dio.patch('/api/mua/client-profiles/$id/', data: updates);
    return ClientBeautyProfile.fromJson(response.data);
  }

  // Product Kit
  Future<List<ProductKitItem>> getProductKit({String? category}) async {
    final response = await _dio.get(
      '/api/mua/product-kit/',
      queryParameters: category != null ? {'category': category} : null,
    );
    return (response.data as List)
        .map((e) => ProductKitItem.fromJson(e))
        .toList();
  }

  Future<ProductKitItem> createProductKitItem(ProductKitItem item) async {
    final response = await _dio.post('/api/mua/product-kit/', data: item.toJson());
    return ProductKitItem.fromJson(response.data);
  }

  Future<ProductKitItem> togglePacked(int id, bool isPacked) async {
    final response = await _dio.patch(
      '/api/mua/product-kit/$id/',
      data: {'is_packed': isPacked},
    );
    return ProductKitItem.fromJson(response.data);
  }

  Future<void> deleteProductKitItem(int id) async {
    await _dio.delete('/api/mua/product-kit/$id/');
  }
}
```

---

## Figma Design Modifications

### Dashboard Layout (MUA-specific sections)

```
┌─────────────────────────────────────────┐
│ 💄 Good Morning, [Name]                 │
│ Makeup Artist Dashboard                 │
├─────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────────────┐ │
│ │ 📅 Next     │ │ 💵 Today's Revenue  │ │
│ │ Appointment │ │ $450.00             │ │
│ │ 2:30 PM     │ │                     │ │
│ │ Sarah J.    │ │ 🚗 Mobile: 3        │ │
│ └─────────────┘ └─────────────────────┘ │
├─────────────────────────────────────────┤
│ 📅 Today's Schedule                     │
│ [Week Calendar Widget - Reuse]          │
├─────────────────────────────────────────┤
│ 📊 Quick Stats                          │
│ ┌───────┐ ┌───────┐ ┌───────┐          │
│ │ 👤 23 │ │ 🎨 12 │ │ 💄 48 │          │
│ │Clients│ │Charts │ │ Kit   │          │
│ └───────┘ └───────┘ └───────┘          │
├─────────────────────────────────────────┤
│ 🎨 Face Charts                 [View All]│
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │
│ │ 📷  │ │ 📷  │ │ 📷  │ │ 📷  │        │
│ │Glam │ │Bridal│ │Natural│ │ + │        │
│ └─────┘ └─────┘ └─────┘ └─────┘        │
├─────────────────────────────────────────┤
│ 💄 Product Kit Checklist       [View All]│
│ ☑ MAC Foundation (2)                    │
│ ☐ Urban Decay Setting Spray             │
│ ☑ Morphe Eyeshadow Palette              │
├─────────────────────────────────────────┤
│ ⭐ Recent Reviews               [View All]│
│ [Reuse existing ReviewCard widget]      │
└─────────────────────────────────────────┘
```

### New Screens Required

1. **Face Charts Screen** (`face_charts_screen.dart`)
   - Grid view of face charts
   - Filter by look type (chips: Natural, Glam, Bridal, Editorial, SFX)
   - Tap to view full image + client info
   - FAB to add new face chart

2. **Client Profile Screen** (`client_profile_screen.dart`)
   - List of client profiles with avatar
   - Shows skin tone, type, foundation shade
   - Tap to edit/view details
   - Search by client name

3. **Client Profile Detail** (`client_profile_detail_screen.dart`)
   - Full profile with all fields
   - Edit mode for updating preferences
   - Link to client's bookings

4. **Product Kit Screen** (`product_kit_screen.dart`)
   - Checklist grouped by category
   - Swipe to delete
   - Toggle packed status with checkbox
   - FAB to add new item

### UI Components to Reuse

| Component | Source | Notes |
|-----------|--------|-------|
| WeekCalendarWidget | Barber dashboard | No changes |
| ReviewCard | Existing reviews | No changes |
| UpcomingAppointmentCard | Barber dashboard | No changes |
| GalleryGrid | Portfolio screen | Adapt for face charts |

---

## Home Screen Integration

### `business_owner_home_screen.dart`

```dart
Widget _buildDashboardContent() {
  final primaryNiche = shopController.shop?.primaryNiche;

  switch (primaryNiche) {
    case 'barber':
      return BarberDashboardContent();
    case 'nail_tech':
      return NailTechDashboardContent();
    case 'tattoo_artist':
      return TattooArtistDashboardContent();
    case 'mua':  // ← ADD THIS
      return MUADashboardContent();
    default:
      return DefaultDashboardContent();
  }
}
```

---

## File Structure

```
lib/features/business_owner/mua/
├── data/
│   └── mua_models.dart
├── services/
│   └── mua_service.dart
├── controllers/
│   ├── mua_dashboard_controller.dart
│   ├── face_chart_controller.dart
│   ├── client_profile_controller.dart
│   └── product_kit_controller.dart
└── presentation/
    ├── widgets/
    │   ├── mua_dashboard_content.dart
    │   ├── face_chart_card.dart
    │   ├── client_profile_card.dart
    │   └── product_kit_item_tile.dart
    └── screens/
        ├── face_charts_screen.dart
        ├── client_profile_screen.dart
        ├── client_profile_detail_screen.dart
        └── product_kit_screen.dart
```

---

## Verification Checklist

```bash
# Run analysis
dart analyze lib/features/business_owner/mua/

# Test with mua niche
# 1. Set shop primary_niche to 'mua'
# 2. Hot reload
# 3. Verify dashboard shows MUA content
# 4. Test Face Charts CRUD
# 5. Test Client Profiles CRUD
# 6. Test Product Kit checklist toggle
```

---

## Summary

| Feature | Backend Status | Flutter Action |
|---------|----------------|----------------|
| Dashboard metrics | ✅ Ready | Build `MUADashboardContent` |
| Face Charts | ✅ Ready | Build grid + detail view |
| Client Profiles | ✅ Ready | Build list + edit form |
| Product Kit | ✅ Ready | Build checklist UI |
| Appointments | ✅ Reuse barber | No changes |
| Revenue | ✅ Reuse barber | No changes |
| Reviews | ✅ Reuse existing | No changes |
