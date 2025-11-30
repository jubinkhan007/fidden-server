# Barber Dashboard - Flutter Implementation Guide

## 🔗 Backend Endpoints

### 1. Today's Appointments
**Endpoint:** `GET /api/barber/today-appointments/`

**Query Parameters:**
- `date` (optional): YYYY-MM-DD format (default: today)

**Response:**
```json
{
  "date": "2025-11-30",
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
      "service_name": "Haircut",
      "service_duration": 30,
      "start_time": "2025-11-30T10:00:00Z",
      "end_time": "2025-11-30T10:30:00Z",
      "status": "active",
      "created_at": "2025-11-25T08:00:00Z"
    }
  ]
}
```

---

### 2. Daily Revenue
**Endpoint:** `GET /api/barber/daily-revenue/`

**Query Parameters:**
- `date` (optional): YYYY-MM-DD format (default: today)

**Response:**
```json
{
  "date": "2025-11-30",
  "total_revenue": 450.00,
  "booking_count": 8,
  "average_booking_value": 56.25
}
```

---

### 3. No-Show Alerts
**Endpoint:** `GET /api/barber/no-show-alerts/`

**Query Parameters:**
- `days` (optional): Number of days to look back (default: 7)

**Response:**
```json
{
  "count": 3,
  "days": 7,
  "no_shows": [
    {
      "id": 456,
      "customer_name": "Jane Smith",
      "customer_email": "jane@example.com",
      "customer_phone": "+1234567890",
      "service_name": "Beard Trim",
      "scheduled_date": "2025-11-29",
      "scheduled_time": "14:00:00",
      "created_at": "2025-11-20T10:00:00Z"
    }
  ]
}
```

---

### 4. Service Menu (Already Existing)
**Endpoints:**
- `GET /api/services/` - List all services
- `POST /api/services/` - Create new service
- `GET /api/services/{id}/` - Get service details
- `PATCH /api/services/{id}/` - Update service
- `DELETE /api/services/{id}/` - Delete service

---

## 📱 Flutter Implementation

### API Service Layer

```dart
class BarberDashboardService {
  final Dio _dio;
  
  BarberDashboardService(this._dio);
  
  Future<TodayAppointmentsResponse> getTodayAppointments({String? date}) async {
    final response = await _dio.get(
      '/api/barber/today-appointments/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return TodayAppointmentsResponse.fromJson(response.data);
  }
  
  Future<DailyRevenueResponse> getDailyRevenue({String? date}) async {
    final response = await _dio.get(
      '/api/barber/daily-revenue/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return DailyRevenueResponse.fromJson(response.data);
  }
  
  Future<NoShowAlertsResponse> getNoShowAlerts({int days = 7}) async {
    final response = await _dio.get(
      '/api/barber/no-show-alerts/',
      queryParameters: {'days': days},
    );
    return NoShowAlertsResponse.fromJson(response.data);
  }
}
```

### Data Models

```dart
class TodayAppointmentsResponse {
  final String date;
  final int count;
  final AppointmentStats stats;
  final List<Appointment> appointments;
  
  TodayAppointmentsResponse.fromJson(Map<String, dynamic> json)
      : date = json['date'],
        count = json['count'],
        stats = AppointmentStats.fromJson(json['stats']),
        appointments = (json['appointments'] as List)
            .map((a) => Appointment.fromJson(a))
            .toList();
}

class AppointmentStats {
  final int confirmed;
  final int completed;
  final int cancelled;
  final int noShow;
  
  AppointmentStats.fromJson(Map<String, dynamic> json)
      : confirmed = json['confirmed'],
        completed = json['completed'],
        cancelled = json['cancelled'],
        noShow = json['no_show'];
}

class Appointment {
  final int id;
  final String customerName;
  final String customerEmail;
  final String serviceName;
  final int serviceDuration;
  final DateTime startTime;
  final DateTime endTime;
  final String status;
  
  Appointment.fromJson(Map<String, dynamic> json)
      : id = json['id'],
        customerName = json['customer_name'],
        customerEmail = json['customer_email'],
        serviceName = json['service_name'],
        serviceDuration = json['service_duration'],
        startTime = DateTime.parse(json['start_time']),
        endTime = DateTime.parse(json['end_time']),
        status = json['status'];
}
```

### Dashboard Widget

```dart
class BarberDashboardScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Barber Dashboard')),
      body: SingleChildScrollView(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Top Section: Stats Cards
            Row(
              children: [
                Expanded(child: _buildTodayAppointmentsCard()),
                SizedBox(width: 12),
                Expanded(child: _buildDailyRevenueCard()),
              ],
            ),
            SizedBox(height: 16),
            
            // No-Show Alerts
            _buildNoShowAlertsCard(),
            SizedBox(height: 16),
            
            // Service Menu
            _buildServiceMenuSection(),
          ],
        ),
      ),
    );
  }
  
  Widget _buildTodayAppointmentsCard() {
    return FutureBuilder<TodayAppointmentsResponse>(
      future: BarberDashboardService(_dio).getTodayAppointments(),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return CircularProgressIndicator();
        
        final data = snapshot.data!;
        return Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('📅 Today\'s Appointments', style: TextStyle(fontWeight: FontWeight.bold)),
                SizedBox(height: 8),
                Text('${data.stats.confirmed} confirmed', style: TextStyle(fontSize: 24)),
                Text('${data.count} total'),
              ],
            ),
          ),
        );
      },
    );
  }
  
  Widget _buildDailyRevenueCard() {
    return FutureBuilder<DailyRevenueResponse>(
      future: BarberDashboardService(_dio).getDailyRevenue(),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return CircularProgressIndicator();
        
        final data = snapshot.data!;
        return Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('💵 Daily Revenue', style: TextStyle(fontWeight: FontWeight.bold)),
                SizedBox(height: 8),
                Text('\$${data.totalRevenue.toStringAsFixed(2)}', style: TextStyle(fontSize: 24)),
                Text('${data.bookingCount} bookings'),
              ],
            ),
          ),
        );
      },
    );
  }
}
```

---

## ✅ Testing

Test the endpoints using:
```bash
# Today's Appointments
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/api/barber/today-appointments/

# Daily Revenue
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/api/barber/daily-revenue/

# No-Show Alerts
curl -H "Authorization: Bearer YOUR_TOKEN" \
 https://your-domain.com/api/barber/no-show-alerts/
```

---

## 🎯 Summary

**Barber Dashboard Features:**
1. ✅ Today's Appointments - Real-time appointment list
2. ✅ Daily Revenue - Revenue tracking and analytics
3. ✅ No-Show Alerts - Recent no-show customers
4. ✅ Service Menu - Existing CRUD endpoints

**All endpoints require authentication** with `IsOwnerRole` permission.
