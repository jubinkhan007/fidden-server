# Flutter Revenue Filtering Guide

## New Feature: Niche-Based Revenue Filtering

The `/api/barber/daily-revenue/` endpoint now supports filtering by service type and niche.

---

## API Endpoint

**GET** `/api/barber/daily-revenue/`

### Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `date` | string | Filter by date (YYYY-MM-DD) | `2025-12-19` |
| `service_type` | string | Filter by specific service type | `facial`, `massage`, `deep_tissue` |
| `niche` | string | Filter by niche category | `esthetician`, `massage`, `hair`, `nail` |

### Niche Values

| Niche | Filters By |
|-------|-----------|
| `esthetician` | Services with `esthetician_service_type` set |
| `massage` | Services with massage-related `esthetician_service_type` |
| `hair` | Services with `hair_service_type` set |
| `nail` | Services with `nail_style_type` set |
| `barber` | All services (no specific filter) |
| `tattoo` | All services (no specific filter) |

---

## Response

```json
{
  "date": "2025-12-19",
  "total_revenue": 450.00,
  "booking_count": 5,
  "average_booking_value": 90.00,
  "filters_applied": {
    "service_type": "facial",
    "niche": null
  }
}
```

---

## Flutter Usage Examples

### 1. Get All Revenue (No Filter)
```dart
final response = await dio.get('/api/barber/daily-revenue/');
```

### 2. Filter by Date
```dart
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {'date': '2025-12-19'});
```

### 3. Filter by Niche
```dart
// Esthetician revenue only
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {'niche': 'esthetician'});

// Massage revenue only
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {'niche': 'massage'});
```

### 4. Filter by Specific Service Type
```dart
// Only facial services
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {'service_type': 'facial'});

// Only deep tissue massage
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {'service_type': 'deep_tissue'});
```

### 5. Combined Filters
```dart
// Esthetician revenue for a specific date
final response = await dio.get('/api/barber/daily-revenue/', 
  queryParameters: {
    'date': '2025-12-19',
    'niche': 'esthetician'
  });
```

---

## Flutter Changes Needed

### 1. Update RevenueService

```dart
class RevenueService {
  static Future<RevenueData> getDailyRevenue({
    String? date,
    String? serviceType,
    String? niche,
  }) async {
    final queryParams = <String, dynamic>{};
    if (date != null) queryParams['date'] = date;
    if (serviceType != null) queryParams['service_type'] = serviceType;
    if (niche != null) queryParams['niche'] = niche;
    
    final response = await dio.get(
      '/api/barber/daily-revenue/',
      queryParameters: queryParams,
    );
    return RevenueData.fromJson(response.data);
  }
}
```

### 2. Update RevenueData Model

```dart
class RevenueData {
  final String date;
  final double totalRevenue;
  final int bookingCount;
  final double averageBookingValue;
  final Map<String, dynamic>? filtersApplied;
  
  RevenueData({
    required this.date,
    required this.totalRevenue,
    required this.bookingCount,
    required this.averageBookingValue,
    this.filtersApplied,
  });
  
  factory RevenueData.fromJson(Map<String, dynamic> json) {
    return RevenueData(
      date: json['date'],
      totalRevenue: (json['total_revenue'] as num).toDouble(),
      bookingCount: json['booking_count'],
      averageBookingValue: (json['average_booking_value'] as num).toDouble(),
      filtersApplied: json['filters_applied'],
    );
  }
}
```

### 3. Update Dashboard Controllers

```dart
// In EstheticianDashboardController
Future<void> loadRevenue() async {
  final revenue = await RevenueService.getDailyRevenue(niche: 'esthetician');
  // ...
}

// In MassageDashboardController  
Future<void> loadRevenue() async {
  final revenue = await RevenueService.getDailyRevenue(niche: 'massage');
  // ...
}
```

---

## Service Type Values

### Esthetician Service Types
`facial`, `massage`, `body`, `wax`, `lash`, `peel`, `microderm`, `wrap`, `scrub`

### Hair Service Types
`cut`, `color`, `style`, `treatment`, `extension`, `braid`, `loc`

### Nail Service Types
`manicure`, `pedicure`, `gel`, `acrylic`, `nail_art`, `dip`
