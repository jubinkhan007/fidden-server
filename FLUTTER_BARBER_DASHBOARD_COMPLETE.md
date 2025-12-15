# Barber Dashboard - Flutter Integration Guide

> **Backend:** Fully implemented on `phase2` branch
> **Endpoints Base URL:** `/api/barber/`

---

## 🎯 Dashboard Overview

The Barber Dashboard provides these features:
1. Today's Appointments
2. Daily Revenue
3. No-Show Alerts
4. **Walk-In Queue** (NEW)
5. **Loyalty Program** (NEW)

---

## 🎨 UI Modification Guide (Figma → Spec)

### ✅ KEEP (In Spec & Has Backend)

| UI Element | Endpoint | Notes |
|------------|----------|-------|
| Niche Chips (top) | `/accounts/me/` → `primary_niche`, `capabilities` | Shows context switching |
| Upcoming Appointment | `today-appointments` | First item in appointments list |
| Today's Schedule (Calendar) | `today-appointments` | Already implemented |
| Today's Earnings | `daily-revenue` → `total_revenue` | ✅ |
| New Booking Requests | `/api/owner-bookings/?status=pending` | Existing endpoint |
| Reviews | `/api/ratings/shop/{id}/` | Existing endpoint |

### ❌ REMOVE (Not in Spec, No Backend)

| UI Element | Reason |
|------------|--------|
| **Monthly Projection** ($48273.89) | Not in barber spec, no endpoint |
| **Top Booked Services Count** (24) | Not in barber spec |
| **Reschedule Counts** (15) | Not in barber spec, no tracking |
| **Active Chairs Overview** (Busy/Finishing/Free) | Not in barber spec |

### 🔄 MODIFY (Exists but Needs Changes)

| UI Element | Change Required |
|------------|-----------------|
| **Design Requests screen** | ❌ This is for **Tattoo Artist only**, not Barber. Remove from barber flow. |
| **Revenue Card** | Show `total_revenue` only, remove "Monthly Projection" |

### ➕ ADD (In Spec, Backend Ready, Missing in Figma)

| Feature | Endpoint | Suggested UI |
|---------|----------|--------------|
| **Walk-In Queue** 🆕 | `GET /api/barber/walk-ins/` | Card showing queue count + list |
| **No-Show Alerts** | `GET /api/barber/no-show-alerts/` | Badge or card with count |
| **Loyalty Program** 🆕 | `GET /api/barber/loyalty/program/` | Card or separate screen |
| **Service Menu Quick Edit** | `GET /api/services/` | Link to service management |

---

## 📊 Recommended Barber Dashboard Layout

```
┌─────────────────────────────────────────┐
│ Good Morning, [Name]          🔔        │
├─────────────────────────────────────────┤
│ [All] [Barber] [Hairstylist] ...        │  ← Niche Chips
├─────────────────────────────────────────┤
│ UPCOMING APPOINTMENT                    │
│ 👤 Jordan Lee • Fade • 11:00 AM     →   │
├─────────────────────────────────────────┤
│ TODAY'S SCHEDULE              Oct 17    │
│ [Sun 17][Mon 18][Tue 19]...             │
├─────────────────────────────────────────┤
│ REVENUE TODAY          │  WALK-INS 🆕   │
│ 💵 $650.00             │  👥 3 waiting  │
├─────────────────────────────────────────┤
│ NO-SHOW ALERTS ⚠️                       │
│ 2 no-shows this week                    │
├─────────────────────────────────────────┤
│ NEW BOOKING REQUESTS           View All │
│ 📋 Petal Wave Cut • Pending        →    │
│ 📋 Angular Fade • Approved         →    │
├─────────────────────────────────────────┤
│ LOYALTY MEMBERS 🎁                      │
│ 25 customers • 5 can redeem rewards     │
├─────────────────────────────────────────┤
│ REVIEWS ⭐                   See all    │
│ Maria Jen ⭐ 5.0                         │
└─────────────────────────────────────────┘
```

---

## 📱 Endpoints & Response Samples

### 1. Today's Appointments
**GET** `/api/barber/today-appointments/`

**Query Params:** `?date=2025-12-15` (optional, default: today)

```json
{
  "date": "2025-12-15",
  "count": 5,
  "stats": {
    "confirmed": 3,
    "completed": 1,
    "cancelled": 1,
    "no_show": 0
  },
  "appointments": [
    {
      "id": 123,
      "customer_name": "John Doe",
      "customer_email": "john@example.com",
      "service_name": "Fade Haircut",
      "service_duration": 30,
      "start_time": "2025-12-15T10:00:00Z",
      "end_time": "2025-12-15T10:30:00Z",
      "status": "active",
      "created_at": "2025-12-10T08:00:00Z"
    }
  ]
}
```

---

### 2. Daily Revenue
**GET** `/api/barber/daily-revenue/`

**Query Params:** `?date=2025-12-15` (optional)

```json
{
  "date": "2025-12-15",
  "total_revenue": 450.00,
  "booking_count": 8,
  "average_booking_value": 56.25
}
```

---

### 3. No-Show Alerts
**GET** `/api/barber/no-show-alerts/`

**Query Params:** `?days=7` (optional, default: 7)

```json
{
  "count": 3,
  "days": 7,
  "no_shows": [
    {
      "id": 45,
      "customer_name": "Jane Smith",
      "customer_email": "jane@example.com",
      "customer_phone": "+1234567890",
      "service_name": "Beard Trim",
      "scheduled_date": "2025-12-12",
      "scheduled_time": "14:00:00",
      "created_at": "2025-12-10T10:00:00Z"
    }
  ]
}
```

---

### 4. Walk-In Queue 🆕

#### Get Queue
**GET** `/api/barber/walk-ins/`

```json
{
  "queue": [
    {
      "id": 1,
      "shop": 1,
      "customer_name": "Walk-in Customer",
      "customer_phone": "555-1234",
      "customer_email": "",
      "user": null,
      "user_name": null,
      "service": 5,
      "service_name": "Buzz Cut",
      "position": 1,
      "estimated_wait_minutes": 15,
      "wait_time_display": "15 min",
      "status": "waiting",
      "notes": "",
      "joined_at": "2025-12-15T10:30:00Z",
      "called_at": null,
      "completed_at": null
    }
  ],
  "waiting_count": 3,
  "in_service_count": 1,
  "total_in_queue": 4
}
```

#### Add to Queue
**POST** `/api/barber/walk-ins/`

**Request:**
```json
{
  "customer_name": "New Customer",
  "customer_phone": "555-5678",
  "service": 5
}
```

#### Update Status
**PATCH** `/api/barber/walk-ins/{id}/`

**Request:**
```json
{
  "status": "in_service"  // waiting | in_service | completed | no_show | cancelled
}
```

#### Remove from Queue
**DELETE** `/api/barber/walk-ins/{id}/`

---

### 5. Loyalty Program 🆕

#### Get Program Settings
**GET** `/api/barber/loyalty/program/`

```json
{
  "id": 1,
  "shop": 1,
  "is_active": true,
  "points_per_dollar": 1.00,
  "points_for_redemption": 100,
  "reward_type": "discount_percent",
  "reward_value": 10.00,
  "created_at": "2025-12-15T10:00:00Z",
  "updated_at": "2025-12-15T10:00:00Z"
}
```

#### Update Program Settings
**PATCH** `/api/barber/loyalty/program/`

**Request:**
```json
{
  "is_active": true,
  "points_per_dollar": 2.00,
  "points_for_redemption": 200,
  "reward_type": "discount_fixed",
  "reward_value": 15.00
}
```

#### List Loyal Customers
**GET** `/api/barber/loyalty/customers/`

```json
{
  "count": 25,
  "customers": [
    {
      "id": 1,
      "shop": 1,
      "user": 42,
      "user_name": "Regular Customer",
      "user_email": "regular@example.com",
      "points_balance": 150,
      "total_points_earned": 500,
      "total_points_redeemed": 350,
      "can_redeem": true,
      "last_earned_at": "2025-12-14T16:00:00Z",
      "last_redeemed_at": "2025-12-01T12:00:00Z"
    }
  ]
}
```

#### Add Points
**POST** `/api/barber/loyalty/add-points/`

**Request:**
```json
{
  "user_id": 42,
  "amount_spent": 50.00
}
```

**Response:**
```json
{
  "points_earned": 50,
  "new_balance": 200,
  "can_redeem": true
}
```

#### Redeem Points
**POST** `/api/barber/loyalty/redeem/`

**Request:**
```json
{
  "user_id": 42
}
```

**Response (Success):**
```json
{
  "success": true,
  "reward_type": "discount_percent",
  "reward_value": 10.00,
  "points_remaining": 50
}
```

---

## 🛠️ Flutter Implementation

### 1. Create Barber Service

```dart
// lib/services/barber_dashboard_service.dart

class BarberDashboardService {
  final Dio _dio;
  
  BarberDashboardService(this._dio);
  
  // Today's Appointments
  Future<TodayAppointmentsResponse> getTodayAppointments({String? date}) async {
    final response = await _dio.get(
      '/api/barber/today-appointments/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return TodayAppointmentsResponse.fromJson(response.data);
  }
  
  // Daily Revenue
  Future<DailyRevenueResponse> getDailyRevenue({String? date}) async {
    final response = await _dio.get(
      '/api/barber/daily-revenue/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return DailyRevenueResponse.fromJson(response.data);
  }
  
  // Walk-In Queue
  Future<WalkInQueueResponse> getWalkInQueue() async {
    final response = await _dio.get('/api/barber/walk-ins/');
    return WalkInQueueResponse.fromJson(response.data);
  }
  
  Future<WalkInEntry> addToQueue({
    required String customerName,
    String? customerPhone,
    int? serviceId,
  }) async {
    final response = await _dio.post('/api/barber/walk-ins/', data: {
      'customer_name': customerName,
      if (customerPhone != null) 'customer_phone': customerPhone,
      if (serviceId != null) 'service': serviceId,
    });
    return WalkInEntry.fromJson(response.data);
  }
  
  Future<void> updateWalkInStatus(int id, String status) async {
    await _dio.patch('/api/barber/walk-ins/$id/', data: {'status': status});
  }
  
  // Loyalty
  Future<LoyaltyProgram> getLoyaltyProgram() async {
    final response = await _dio.get('/api/barber/loyalty/program/');
    return LoyaltyProgram.fromJson(response.data);
  }
  
  Future<LoyaltyCustomersResponse> getLoyaltyCustomers() async {
    final response = await _dio.get('/api/barber/loyalty/customers/');
    return LoyaltyCustomersResponse.fromJson(response.data);
  }
  
  Future<AddPointsResponse> addLoyaltyPoints(int userId, double amount) async {
    final response = await _dio.post('/api/barber/loyalty/add-points/', data: {
      'user_id': userId,
      'amount_spent': amount,
    });
    return AddPointsResponse.fromJson(response.data);
  }
}
```

### 2. Models

```dart
// lib/models/barber_dashboard.dart

class WalkInEntry {
  final int id;
  final String customerName;
  final String? customerPhone;
  final String? serviceName;
  final int position;
  final int estimatedWaitMinutes;
  final String waitTimeDisplay;
  final String status;
  final DateTime joinedAt;
  
  // fromJson...
}

class LoyaltyProgram {
  final bool isActive;
  final double pointsPerDollar;
  final int pointsForRedemption;
  final String rewardType; // discount_percent | discount_fixed | free_service
  final double rewardValue;
  
  // fromJson...
}

class LoyaltyCustomer {
  final int userId;
  final String userName;
  final String userEmail;
  final int pointsBalance;
  final bool canRedeem;
  
  // fromJson...
}
```

### 3. Dashboard Screen Structure

```dart
// lib/screens/barber/barber_dashboard_screen.dart

class BarberDashboardScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            // Hero Section
            _TodayAppointmentsCard(),
            _DailyRevenueCard(),
            
            // Walk-In Queue
            _WalkInQueueCard(),
            
            // No-Show Alerts
            _NoShowAlertsCard(),
            
            // Loyalty Program Summary
            _LoyaltyProgramCard(),
          ],
        ),
      ),
    );
  }
}
```

---

## 🔗 UI Component Mapping

| UI Element | Endpoint | Data Field |
|------------|----------|------------|
| Today's Schedule Calendar | `today-appointments` | `appointments` |
| Revenue Card | `daily-revenue` | `total_revenue` |
| Booking Count | `daily-revenue` | `booking_count` |
| Walk-In Queue List | `walk-ins` | `queue` |
| Queue Position Badge | `walk-ins` | `position` |
| Wait Time Display | `walk-ins` | `wait_time_display` |
| No-Show Alert Badge | `no-show-alerts` | `count` |
| Loyalty Points Balance | `loyalty/customers` | `points_balance` |
| Redeem Button Enabled | `loyalty/customers` | `can_redeem` |

---

## ✅ Checklist

- [ ] Create `BarberDashboardService`
- [ ] Create data models
- [ ] Build `BarberDashboardScreen`
- [ ] Implement Walk-In Queue UI with status updates
- [ ] Implement Loyalty Program settings screen
- [ ] Add points after booking completion
- [ ] Show redeem option when `can_redeem: true`
