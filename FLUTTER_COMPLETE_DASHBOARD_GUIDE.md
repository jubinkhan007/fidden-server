# Flutter Multi-Niche Dashboard - Complete Implementation Guide

**Target:** Flutter AI Agent  
**Backend:** Fidden Server (phase2 branch)  
**Architecture:** Single Home Dashboard with Primary Niche + Capabilities

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Authentication Setup](#authentication-setup)
3. [Multi-Niche Data Structure](#multi-niche-data-structure)
4. [Dashboard Routing Logic](#dashboard-routing-logic)
5. [Barber Dashboard Implementation](#barber-dashboard-implementation)
6. [Tattoo Artist Dashboard](#tattoo-artist-dashboard)
7. [Testing](#testing)

---

## 🏗️ Architecture Overview

### Key Concepts

**Primary Niche + Capabilities Model:**
- Each shop has **ONE primary niche** (drives the main dashboard layout)
- Shops can have **capabilities** (additional service types)
- **One unified Home dashboard** (not separate dashboards per niche)
- **Context chips** filter/reorder sections (don't route to different pages)

**Example:**
```json
{
  "primary_niche": "barber",
  "capabilities": ["massage_therapist", "esthetician"],
  "shop_niches": ["barber", "massage_therapist", "esthetician"]
}
```

**Dashboard Behavior:**
- **Hero Section:** Always shows tiles for `primary_niche`
- **Secondary Sections:** Show tiles for each `capability`
- **Context Chips:** `All • Barber • Massage • Esthetician`
- **Chip Tap:** Reorders sections, doesn't navigate away

---

## 🔐 Authentication Setup

### 1. API Service Configuration

```dart
// lib/services/api_service.dart
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  static const String baseUrl = 'https://your-domain.com';
  late Dio _dio;
  
  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: Duration(seconds: 30),
      receiveTimeout: Duration(seconds: 30),
    ));
    
    // Add interceptor for authentication
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final prefs = await SharedPreferences.getInstance();
        final token = prefs.getString('access_token');
        
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        
        return handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Handle token refresh or logout
          await _handleUnauthorized();
        }
        return handler.next(error);
      },
    ));
  }
  
  Dio get dio => _dio;
  
  Future<void> _handleUnauthorized() async {
    // Implement token refresh or logout logic
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
    // Navigate to login screen
  }
}
```

### 2. Login Flow

```dart
// lib/services/auth_service.dart
class AuthService {
  final ApiService _apiService;
  
  AuthService(this._apiService);
  
  Future<LoginResponse> login(String email, String password) async {
    final response = await _apiService.dio.post(
      '/accounts/login/',
      data: {'email': email, 'password': password},
    );
    
    final loginData = LoginResponse.fromJson(response.data);
    
    // Store tokens and shop data
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', loginData.accessToken);
    await prefs.setString('refresh_token', loginData.refreshToken);
    await prefs.setInt('shop_id', loginData.shopId ?? 0);
    await prefs.setString('primary_niche', loginData.primaryNiche ?? 'other');
    await prefs.setStringList('capabilities', loginData.capabilities ?? []);
    
    return loginData;
  }
}

class LoginResponse {
  final bool success;
  final String email;
  final String role;
  final int? shopId;
  final String? primaryNiche;
  final List<String>? capabilities;
  final List<String>? shopNiches;
  final String accessToken;
  final String refreshToken;
  
  LoginResponse.fromJson(Map<String, dynamic> json)
      : success = json['success'],
        email = json['email'],
        role = json['role'],
        shopId = json['shop_id'],
        primaryNiche = json['primary_niche'],
        capabilities = json['capabilities'] != null 
            ? List<String>.from(json['capabilities'])
            : null,
        shopNiches = json['shop_niches'] != null
            ? List<String>.from(json['shop_niches'])
            : null,
        accessToken = json['accessToken'],
        refreshToken = json['refreshToken'];
}
```

---

## 📊 Multi-Niche Data Structure

### User/Shop Model

```dart
// lib/models/user.dart
class User {
  final int id;
  final String email;
  final String name;
  final int? shopId;
  final String? primaryNiche;
  final List<String> capabilities;
  final List<String> shopNiches;
  
  User.fromJson(Map<String, dynamic> json)
      : id = json['id'],
        email = json['email'],
        name = json['name'] ?? '',
        shopId = json['shop_id'],
        primaryNiche = json['primary_niche'],
        capabilities = json['capabilities'] != null
            ? List<String>.from(json['capabilities'])
            : [],
        shopNiches = json['shop_niches'] != null
            ? List<String>.from(json['shop_niches'])
            : [];
  
  // Helper methods
  bool hasNiche(String niche) => shopNiches.contains(niche);
  bool hasCapability(String capability) => capabilities.contains(capability);
  List<String> get allNiches => shopNiches;
}
```

---

## 🎯 Dashboard Routing Logic

### Main Dashboard Screen

```dart
// lib/screens/home_dashboard.dart
import 'package:flutter/material.dart';

class HomeDashboard extends StatefulWidget {
  final User user;
  
  const HomeDashboard({required this.user});

  @override
  _HomeDashboardState createState() => _HomeDashboardState();
}

class _HomeDashboardState extends State<HomeDashboard> {
  String _activeFilter = 'All';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Dashboard'),
        bottom: PreferredSize(
          preferredSize: Size.fromHeight(60),
          child: _buildContextChips(),
        ),
      ),
      body: CustomScrollView(
        slivers: [
          // Hero Section (Primary Niche)
          if (_shouldShowSection(widget.user.primaryNiche))
            _buildHeroSection(widget.user.primaryNiche!),
          
          // Capability Sections
          ...widget.user.capabilities.map((capability) {
            if (_shouldShowSection(capability)) {
              return _buildCapabilitySection(capability);
            }
            return SliverToBoxAdapter(child: SizedBox.shrink());
          }).toList(),
        ],
      ),
    );
  }
  
  bool _shouldShowSection(String? niche) {
    if (niche == null) return false;
    return _activeFilter == 'All' || _activeFilter == niche;
  }
  
  Widget _buildContextChips() {
    final allNiches = [
      widget.user.primaryNiche,
      ...widget.user.capabilities
    ].whereType<String>().toList();
    
    return Container(
      height: 60,
      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          _buildChip('All', _activeFilter == 'All'),
          SizedBox(width: 8),
          ...allNiches.map((niche) => Padding(
            padding: EdgeInsets.only(right: 8),
            child: _buildChip(_getNicheName(niche), _activeFilter == niche),
          )),
        ],
      ),
    );
  }
  
  Widget _buildChip(String label, bool isSelected) {
    return FilterChip(
      label: Text(label),
      selected: isSelected,
      onSelected: (selected) {
        setState(() {
          _activeFilter = selected ? label : 'All';
        });
      },
      backgroundColor: Colors.grey[200],
      selectedColor: Theme.of(context).primaryColor,
      labelStyle: TextStyle(
        color: isSelected ? Colors.white : Colors.black87,
        fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
      ),
    );
  }
  
  String _getNicheName(String niche) {
    const nicheNames = {
      'barber': 'Barber',
      'tattoo_artist': 'Tattoo Artist',
      'hairstylist': 'Hairstylist',
      'massage_therapist': 'Massage',
      'esthetician': 'Esthetician',
      'nail_tech': 'Nail Tech',
      'makeup_artist': 'Makeup Artist',
      'fitness_trainer': 'Fitness',
    };
    return nicheNames[niche] ?? niche;
  }
  
  Widget _buildHeroSection(String niche) {
    return SliverToBoxAdapter(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'Primary Dashboard',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
          ),
          _buildNicheWidgets(niche, isHero: true),
        ],
      ),
    );
  }
  
  Widget _buildCapabilitySection(String niche) {
    return SliverToBoxAdapter(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              '${_getNicheName(niche)} Services',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
          ),
          _buildNicheWidgets(niche, isHero: false),
        ],
      ),
    );
  }
  
  Widget _buildNicheWidgets(String niche, {required bool isHero}) {
    switch (niche) {
      case 'barber':
        return BarberDashboardWidgets(isHero: isHero);
      case 'tattoo_artist':
        return TattooArtistDashboardWidgets(isHero: isHero);
      // Add other niches as they're implemented
      default:
        return GenericDashboardWidgets();
    }
  }
}
```

---

## ✂️ Barber Dashboard Implementation

### API Endpoints

```dart
// lib/services/barber_dashboard_service.dart
class BarberDashboardService {
  final ApiService _apiService;
  
  BarberDashboardService(this._apiService);
  
  /// GET /api/barber/today-appointments/
  Future<TodayAppointmentsResponse> getTodayAppointments({String? date}) async {
    final response = await _apiService.dio.get(
      '/api/barber/today-appointments/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return TodayAppointmentsResponse.fromJson(response.data);
  }
  
  /// GET /api/barber/daily-revenue/
  Future<DailyRevenueResponse> getDailyRevenue({String? date}) async {
    final response = await _apiService.dio.get(
      '/api/barber/daily-revenue/',
      queryParameters: date != null ? {'date': date} : null,
    );
    return DailyRevenueResponse.fromJson(response.data);
  }
  
  /// GET /api/barber/no-show-alerts/
  Future<NoShowAlertsResponse> getNoShowAlerts({int days = 7}) async {
    final response = await _apiService.dio.get(
      '/api/barber/no-show-alerts/',
      queryParameters: {'days': days},
    );
    return NoShowAlertsResponse.fromJson(response.data);
  }
}
```

### Data Models

```dart
// lib/models/barber_models.dart

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

class DailyRevenueResponse {
  final String date;
  final double totalRevenue;
  final int bookingCount;
  final double averageBookingValue;
  
  DailyRevenueResponse.fromJson(Map<String, dynamic> json)
      : date = json['date'],
        totalRevenue = (json['total_revenue'] as num).toDouble(),
        bookingCount = json['booking_count'],
        averageBookingValue = (json['average_booking_value'] as num).toDouble();
}

class NoShowAlertsResponse {
  final int count;
  final int days;
  final List<NoShowAlert> noShows;
  
  NoShowAlertsResponse.fromJson(Map<String, dynamic> json)
      : count = json['count'],
        days = json['days'],
        noShows = (json['no_shows'] as List)
            .map((n) => NoShowAlert.fromJson(n))
            .toList();
}

class NoShowAlert {
  final int id;
  final String customerName;
  final String customerEmail;
  final String? customerPhone;
  final String serviceName;
  final String scheduledDate;
  final String scheduledTime;
  
  NoShowAlert.fromJson(Map<String, dynamic> json)
      : id = json['id'],
        customerName = json['customer_name'],
        customerEmail = json['customer_email'],
        customerPhone = json['customer_phone'],
        serviceName = json['service_name'],
        scheduledDate = json['scheduled_date'],
        scheduledTime = json['scheduled_time'];
}
```

### Barber Dashboard Widgets

```dart
// lib/widgets/barber_dashboard_widgets.dart

class BarberDashboardWidgets extends StatelessWidget {
  final bool isHero;
  
  const BarberDashboardWidgets({required this.isHero});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Top Stats Row
        Row(
          children: [
            Expanded(child: _TodayAppointmentsCard()),
            SizedBox(width: 12),
            Expanded(child: _DailyRevenueCard()),
          ],
        ),
        SizedBox(height: 16),
        
        // No-Show Alerts
        _NoShowAlertsCard(),
        
        // Service Menu (if hero section)
        if (isHero) ...[
          SizedBox(height: 16),
          _ServiceMenuCard(),
        ],
      ],
    );
  }
}

class _TodayAppointmentsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final service = BarberDashboardService(context.read<ApiService>());
    
    return FutureBuilder<TodayAppointmentsResponse>(
      future: service.getTodayAppointments(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildLoadingCard('📅 Today\'s Appointments');
        }
        
        if (!snapshot.hasData) {
          return _buildErrorCard('📅 Today\'s Appointments');
        }
        
        final data = snapshot.data!;
        return Card(
          elevation: 2,
          child: InkWell(
            onTap: () => _showAppointmentsList(context, data.appointments),
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '📅 Today\'s Appointments',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Colors.grey[700],
                    ),
                  ),
                  SizedBox(height: 12),
                  Text(
                    '${data.stats.confirmed}',
                    style: TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: Theme.of(context).primaryColor,
                    ),
                  ),
                  Text(
                    'confirmed',
                    style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                  ),
                  SizedBox(height: 8),
                  Row(
                    children: [
                      _buildStatChip('✅ ${data.stats.completed}', Colors.green),
                      SizedBox(width: 4),
                      _buildStatChip('❌ ${data.stats.cancelled}', Colors.orange),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
  
  Widget _buildStatChip(String label, Color color) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
  
  void _showAppointmentsList(BuildContext context, List<Appointment> appointments) {
    // Navigate to full appointments list screen
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AppointmentsListScreen(appointments: appointments),
      ),
    );
  }
}

class _DailyRevenueCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final service = BarberDashboardService(context.read<ApiService>());
    
    return FutureBuilder<DailyRevenueResponse>(
      future: service.getDailyRevenue(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildLoadingCard('💵 Daily Revenue');
        }
        
        if (!snapshot.hasData) {
          return _buildErrorCard('💵 Daily Revenue');
        }
        
        final data = snapshot.data!;
        return Card(
          elevation: 2,
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '💵 Daily Revenue',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey[700],
                  ),
                ),
                SizedBox(height: 12),
                Text(
                  '\$${data.totalRevenue.toStringAsFixed(2)}',
                  style: TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                    color: Colors.green[700],
                  ),
                ),
                Text(
                  '${data.bookingCount} bookings',
                  style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                ),
                SizedBox(height: 8),
                Container(
                  padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.blue.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Avg: \$${data.averageBookingValue.toStringAsFixed(2)}',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.blue[700],
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _NoShowAlertsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final service = BarberDashboardService(context.read<ApiService>());
    
    return FutureBuilder<NoShowAlertsResponse>(
      future: service.getNoShowAlerts(),
      builder: (context, snapshot) {
        if (!snapshot.hasData || snapshot.data!.count == 0) {
          return SizedBox.shrink();
        }
        
        final data = snapshot.data!;
        return Card(
          color: Colors.orange[50],
          elevation: 2,
          child: ListTile(
            leading: Icon(Icons.warning_amber_rounded, color: Colors.orange[700]),
            title: Text(
              '🔁 ${data.count} No-Show Alert${data.count > 1 ? 's' : ''}',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            subtitle: Text('Last ${data.days} days'),
            trailing: Icon(Icons.chevron_right),
            onTap: () {
              // Navigate to no-show details
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => NoShowAlertsScreen(alerts: data.noShows),
                ),
              );
            },
          ),
        );
      },
    );
  }
}

// Helper widgets
Widget _buildLoadingCard(String title) {
  return Card(
    child: Padding(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(fontWeight: FontWeight.w600)),
          SizedBox(height: 12),
          Center(child: CircularProgressIndicator()),
        ],
      ),
    ),
  );
}

Widget _buildErrorCard(String title) {
  return Card(
    child: Padding(
      padding: EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(fontWeight: FontWeight.w600)),
          SizedBox(height: 12),
          Text('Failed to load', style: TextStyle(color: Colors.red)),
        ],
      ),
    ),
  );
}
```

---

## 🖋️ Tattoo Artist Dashboard

### Existing Backend Endpoints

The Tattoo Artist dashboard is **already implemented** on the backend. Use these endpoints:

```dart
// lib/services/tattoo_dashboard_service.dart
class TattooDashboardService {
  final ApiService _apiService;
  
  TattooDashboardService(this._apiService);
  
  // Portfolio
  Future<List<PortfolioItem>> getPortfolio() async {
    final response = await _apiService.dio.get('/api/portfolio/');
    return (response.data as List)
        .map((item) => PortfolioItem.fromJson(item))
        .toList();
  }
  
  // Design Requests
  Future<List<DesignRequest>> getDesignRequests() async {
    final response = await _apiService.dio.get('/api/design-requests/');
    return (response.data as List)
        .map((req) => DesignRequest.fromJson(req))
        .toList();
  }
  
  // Consent Forms
  Future<List<ConsentForm>> getConsentForms() async {
    final response = await _apiService.dio.get('/api/consent-forms/templates/');
    return (response.data as List)
        .map((form) => ConsentForm.fromJson(form))
        .toList();
  }
}
```

**Reference:** See the existing `flutter_tailored_dashboard_guide.md` for complete Tattoo Artist implementation details.

---

## ✅ Testing

### Manual Testing Checklist

**1. Authentication:**
- [ ] Login returns `primary_niche` and `capabilities`
- [ ] Tokens stored correctly in SharedPreferences
- [ ] API requests include Authorization header

**2. Dashboard Routing:**
- [ ] Home screen shows correct Hero section based on `primary_niche`
- [ ] Capability sections appear below Hero section
- [ ] Context chips filter/reorder correctly (don't navigate away)

**3. Barber Dashboard:**
- [ ] Today's Appointments loads correctly
- [ ] Daily Revenue displays accurate data
- [ ] No-Show Alerts appear when applicable
- [ ] Service Menu accessible

**4. Tattoo Dashboard (if applicable):**
- [ ] Portfolio items load
- [ ] Design Requests display
- [ ] Consent Forms accessible

---

## 🎯 Implementation Checklist

- [ ] Set up `ApiService` with authentication interceptor
- [ ] Implement `AuthService` with login flow
- [ ] Create `User` model with niche fields
- [ ] Build `HomeDashboard` with context chips
- [ ] Implement `BarberDashboardWidgets`
- [ ] Test multi-niche routing logic
- [ ] Handle edge cases (no shop, single niche, etc.)

---

## 📞 Support

**Backend Repository:** `jubinkhan007/fidden-server` (phase2 branch)

**Key Files:**
- Barber endpoints: `api/barber_views.py`
- Tattoo endpoints: `api/views.py` (ViewSets)
- Authentication: `accounts/views.py`

**Need Help?** Test endpoints using:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/api/barber/today-appointments/
```
