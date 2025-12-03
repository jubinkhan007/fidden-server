# Consultation Calendar - API Reference

**Backend Status:** ✅ Fully Implemented  
**Base URL:** `/api/consultations/`  
**Authentication:** Bearer Token Required  
**Permissions:** `IsOwnerRole` (Shop owners only)

---

## Overview

Pre-tattoo consultation appointment management for tattoo artists. Allows scheduling, tracking, and managing customer consultations.

---

## Data Model

```json
{
  "id": 1,
  "shop": 7,
  "customer_name": "Sarah Lee",
  "customer_email": "sarah@example.com",
  "customer_phone": "+1234567890",
  "date": "2025-12-05",
  "time": "14:00:00",
  "duration_minutes": 30,
  "status": "confirmed",
  "notes": "Wants floral sleeve design",
  "design_reference_images": [
    "https://bucket.s3.amazonaws.com/ref1.jpg"
  ],
  "created_at": "2025-11-30T10:00:00Z",
  "updated_at": "2025-11-30T10:00:00Z"
}
```

**Status Values:** `scheduled`, `confirmed`, `completed`, `cancelled`, `no_show`

---

## API Endpoints

### 1. List Consultations

```http
GET /api/consultations/
```

**Query Parameters:**
- `date_from` (optional): YYYY-MM-DD
- `date_to` (optional): YYYY-MM-DD  
- `status` (optional): Filter by status

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "shop": 7,
    "customer_name": "Sarah Lee",
    "customer_email": "sarah@example.com",
    "customer_phone": "+1234567890",
    "date": "2025-12-05",
    "time": "14:00:00",
    "duration_minutes": 30,
    "status": "confirmed",
    "notes": "Wants floral sleeve design",
    "design_reference_images": [],
    "created_at": "2025-11-30T10:00:00Z",
    "updated_at": "2025-11-30T10:00:00Z"
  }
]
```

---

### 2. Create Consultation

```http
POST /api/consultations/
Content-Type: application/json
```

**Request Body:**
```json
{
  "customer_name": "Mike Brown",
  "customer_email": "mike@example.com",
  "customer_phone": "+0987654321",
  "date": "2025-12-10",
  "time": "15:30:00",
  "duration_minutes": 45,
  "notes": "Interested in biomechanical design"
}
```

**Response:** `201 Created`
```json
{
  "id": 2,
  "shop": 7,
  "customer_name": "Mike Brown",
  "customer_email": "mike@example.com",
  "customer_phone": "+0987654321",
  "date": "2025-12-10",
  "time": "15:30:00",
  "duration_minutes": 45,
  "status": "scheduled",
  "notes": "Interested in biomechanical design",
  "design_reference_images": [],
  "created_at": "2025-12-01T10:00:00Z",
  "updated_at": "2025-12-01T10:00:00Z"
}
```

---

### 3. Get Consultation Details

```http
GET /api/consultations/{id}/
```

**Response:** `200 OK` - Same format as list item

---

### 4. Update Consultation

```http
PATCH /api/consultations/{id}/
Content-Type: application/json
```

**Request Body (all fields optional):**
```json
{
  "date": "2025-12-11",
  "time": "16:00:00",
  "notes": "Updated notes",
  "duration_minutes": 60
}
```

**Response:** `200 OK` - Updated consultation object

---

### 5. Delete Consultation

```http
DELETE /api/consultations/{id}/
```

**Response:** `204 No Content`

---

### 6. Confirm Consultation

```http
POST /api/consultations/{id}/confirm/
```

**Request Body:** None

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "confirmed",
  ...
}
```

---

### 7. Complete Consultation

```http
POST /api/consultations/{id}/complete/
Content-Type: application/json
```

**Request Body (optional):**
```json
{
  "notes": "Client approved design. Ready to schedule tattoo session."
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "completed",
  "notes": "Client approved design. Ready to schedule tattoo session.",
  ...
}
```

---

### 8. Cancel Consultation

```http
POST /api/consultations/{id}/cancel/
```

**Request Body:** None

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "cancelled",
  ...
}
```

---

### 9. Mark No-Show

```http
POST /api/consultations/{id}/mark_no_show/
```

**Request Body:** None

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "no_show",
  ...
}
```

---

## Notes

- **Time Format:** 24-hour format (HH:MM:SS), e.g., "14:30:00"
- **Date Format:** YYYY-MM-DD
- **Unique Constraint:** (shop, date, time) - prevents double-booking
- **Auto-Assignment:** `shop` field is automatically set from authenticated user
- **Design Images:** `design_reference_images` is a JSON array of image URLs

---

## Error Responses

**400 Bad Request** - Validation error or time slot conflict  
**401 Unauthorized** - Missing or invalid token  
**403 Forbidden** - Not a shop owner  
**404 Not Found** - Consultation doesn't exist  
**500 Internal Server Error** - Server error


---

## 📋 Overview

The Consultation Calendar feature allows tattoo artists to schedule, manage, and track pre-tattoo consultation appointments with customers.

### Key Features
- Schedule consultation appointments
- Filter by date range and status
- Confirm/complete/cancel consultations
- Mark customers as no-show
- Store design reference images
- Add consultation notes

---

## 🔌 API Endpoints

### Base URL
```
Production: https://fidden-server-2.onrender.com/api
Local: http://localhost:8000/api
```

### Authentication
All endpoints require Bearer token:
```
Authorization: Bearer <access_token>
```

### Endpoints

#### 1. List Consultations
```http
GET /api/consultations/
Query Parameters:
  - date_from: YYYY-MM-DD (optional)
  - date_to: YYYY-MM-DD (optional)
  - status: scheduled|confirmed|completed|cancelled|no_show (optional)
```

**Response:**
```json
[
  {
    "id": 1,
    "shop": 7,
    "customer_name": "Sarah Lee",
    "customer_email": "sarah@example.com",
    "customer_phone": "+1234567890",
    "date": "2025-12-05",
    "time": "14:00:00",
    "duration_minutes": 30,
    "status": "confirmed",
    "notes": "Wants floral sleeve design, bring reference images",
    "design_reference_images": [
      "https://bucket.s3.amazonaws.com/ref1.jpg",
      "https://bucket.s3.amazonaws.com/ref2.jpg"
    ],
    "created_at": "2025-11-30T10:00:00Z",
    "updated_at": "2025-11-30T10:00:00Z"
  }
]
```

#### 2. Create Consultation
```http
POST /api/consultations/
Content-Type: application/json
```

**Request Body:**
```json
{
  "customer_name": "Mike Brown",
  "customer_email": "mike@example.com",
  "customer_phone": "+0987654321",
  "date": "2025-12-10",
  "time": "15:30:00",
  "duration_minutes": 45,
  "notes": "Interested in biomechanical design"
}
```

**Response:** Same as list item

#### 3. Update Consultation
```http
PATCH /api/consultations/{id}/
Content-Type: application/json
```

**Request Body:**
```json
{
  "date": "2025-12-11",
  "time": "16:00:00",
  "notes": "Updated notes"
}
```

#### 4. Delete Consultation
```http
DELETE /api/consultations/{id}/
```

#### 5. Confirm Consultation
```http
POST /api/consultations/{id}/confirm/
```

**Response:** Updated consultation object with status = "confirmed"

#### 6. Complete Consultation
```http
POST /api/consultations/{id}/complete/
Content-Type: application/json
```

**Request Body (optional):**
```json
{
  "notes": "Client approved the design. Ready to schedule tattoo session."
}
```

#### 7. Cancel Consultation
```http
POST /api/consultations/{id}/cancel/
```

#### 8. Mark No-Show
```http
POST /api/consultations/{id}/mark_no_show/
```

---

## 📱 Flutter Implementation

### Step 1: Create Data Model

```dart
// lib/models/consultation.dart
class Consultation {
  final int id;
  final int shop;
  final String customerName;
  final String customerEmail;
  final String? customerPhone;
  final DateTime date;
  final TimeOfDay time;
  final int durationMinutes;
  final String status; // scheduled, confirmed, completed, cancelled, no_show
  final String notes;
  final List<String> designReferenceImages;
  final DateTime createdAt;
  final DateTime updatedAt;

  Consultation({
    required this.id,
    required this.shop,
    required this.customerName,
    required this.customerEmail,
    this.customerPhone,
    required this.date,
    required this.time,
    required this.durationMinutes,
    required this.status,
    required this.notes,
    required this.designReferenceImages,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Consultation.fromJson(Map<String, dynamic> json) {
    // Parse time from "HH:MM:SS" format
    final timeParts = (json['time'] as String).split(':');
    final hour = int.parse(timeParts[0]);
    final minute = int.parse(timeParts[1]);

    return Consultation(
      id: json['id'],
      shop: json['shop'],
      customerName: json['customer_name'],
      customerEmail: json['customer_email'],
      customerPhone: json['customer_phone'],
      date: DateTime.parse(json['date']),
      time: TimeOfDay(hour: hour, minute: minute),
      durationMinutes: json['duration_minutes'],
      status: json['status'],
      notes: json['notes'] ?? '',
      designReferenceImages: List<String>.from(json['design_reference_images'] ?? []),
      createdAt: DateTime.parse(json['created_at']),
      updatedAt: DateTime.parse(json['updated_at']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'customer_name': customerName,
      'customer_email': customerEmail,
      'customer_phone': customerPhone,
      'date': date.toIso8601String().split('T')[0], // YYYY-MM-DD
      'time': '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}:00',
      'duration_minutes': durationMinutes,
      'notes': notes,
    };
  }

  // Helper getters
  String get formattedDate => '${date.month}/${date.day}/${date.year}';
  String get formattedTime => '${time.hourOfPeriod}:${time.minute.toString().padLeft(2, '0')} ${time.period == DayPeriod.am ? 'AM' : 'PM'}';
  
  Color get statusColor {
    switch (status) {
      case 'confirmed':
        return Colors.green;
      case 'completed':
        return Colors.blue;
      case 'cancelled':
        return Colors.red;
      case 'no_show':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  String get statusLabel {
    return status.split('_').map((word) => word[0].toUpperCase() + word.substring(1)).join(' ');
  }
}
```

### Step 2: Create API Service

```dart
// lib/services/consultation_service.dart
import 'package:dio/dio.dart';
import '../models/consultation.dart';

class ConsultationService {
  final Dio _dio;

  ConsultationService(this._dio);

  /// List consultations with optional filters
  Future<List<Consultation>> getConsultations({
    DateTime? dateFrom,
    DateTime? dateTo,
    String? status,
  }) async {
    final queryParams = <String, dynamic>{};
    
    if (dateFrom != null) {
      queryParams['date_from'] = dateFrom.toIso8601String().split('T')[0];
    }
    if (dateTo != null) {
      queryParams['date_to'] = dateTo.toIso8601String().split('T')[0];
    }
    if (status != null) {
      queryParams['status'] = status;
    }

    final response = await _dio.get(
      '/api/consultations/',
      queryParameters: queryParams,
    );

    return (response.data as List)
        .map((json) => Consultation.fromJson(json))
        .toList();
  }

  /// Create new consultation
  Future<Consultation> createConsultation(Consultation consultation) async {
    final response = await _dio.post(
      '/api/consultations/',
      data: consultation.toJson(),
    );

    return Consultation.fromJson(response.data);
  }

  /// Update consultation
  Future<Consultation> updateConsultation(int id, Map<String, dynamic> updates) async {
    final response = await _dio.patch(
      '/api/consultations/$id/',
      data: updates,
    );

    return Consultation.fromJson(response.data);
  }

  /// Delete consultation
  Future<void> deleteConsultation(int id) async {
    await _dio.delete('/api/consultations/$id/');
  }

  /// Confirm consultation
  Future<Consultation> confirmConsultation(int id) async {
    final response = await _dio.post('/api/consultations/$id/confirm/');
    return Consultation.fromJson(response.data);
  }

  /// Complete consultation
  Future<Consultation> completeConsultation(int id, {String? notes}) async {
    final response = await _dio.post(
      '/api/consultations/$id/complete/',
      data: notes != null ? {'notes': notes} : null,
    );
    return Consultation.fromJson(response.data);
  }

  /// Cancel consultation
  Future<Consultation> cancelConsultation(int id) async {
    final response = await _dio.post('/api/consultations/$id/cancel/');
    return Consultation.fromJson(response.data);
  }

  /// Mark as no-show
  Future<Consultation> markNoShow(int id) async {
    final response = await _dio.post('/api/consultations/$id/mark_no_show/');
    return Consultation.fromJson(response.data);
  }
}
```

### Step 3: Create UI - Consultation List Screen

```dart
// lib/screens/consultations/consultation_list_screen.dart
import 'package:flutter/material.dart';
import '../../models/consultation.dart';
import '../../services/consultation_service.dart';

class ConsultationListScreen extends StatefulWidget {
  @override
  _ConsultationListScreenState createState() => _ConsultationListScreenState();
}

class _ConsultationListScreenState extends State<ConsultationListScreen> {
  final ConsultationService _service = ConsultationService(dio); // Your Dio instance
  List<Consultation> _consultations = [];
  bool _loading = true;
  String? _statusFilter;
  DateTime? _dateFrom;
  DateTime? _dateTo;

  @override
  void initState() {
    super.initState();
    _loadConsultations();
  }

  Future<void> _loadConsultations() async {
    setState(() => _loading = true);
    try {
      final consultations = await _service.getConsultations(
        dateFrom: _dateFrom,
        dateTo: _dateTo,
        status: _statusFilter,
      );
      setState(() {
        _consultations = consultations;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error loading consultations: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Consultations'),
        actions: [
          // Filter button
          IconButton(
            icon: Icon(Icons.filter_list),
            onPressed: _showFilterDialog,
          ),
        ],
      ),
      body: _loading
          ? Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadConsultations,
              child: _consultations.isEmpty
                  ? _buildEmptyState()
                  : ListView.builder(
                      itemCount: _consultations.length,
                      itemBuilder: (context, index) {
                        return _buildConsultationCard(_consultations[index]);
                      },
                    ),
            ),
      floatingActionButton: FloatingActionButton(
        child: Icon(Icons.add),
        onPressed: () => _navigateToCreateConsultation(),
      ),
    );
  }

  Widget _buildConsultationCard(Consultation consultation) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: ListTile(
        leading: Container(
          width: 60,
          padding: EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: consultation.statusColor.withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                consultation.date.day.toString(),
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: consultation.statusColor,
                ),
              ),
              Text(
                _getMonthAbbr(consultation.date.month),
                style: TextStyle(
                  fontSize: 12,
                  color: consultation.statusColor,
                ),
              ),
            ],
          ),
        ),
        title: Text(consultation.customerName),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: 4),
            Row(
              children: [
                Icon(Icons.access_time, size: 14),
                SizedBox(width: 4),
                Text(consultation.formattedTime),
                SizedBox(width: 16),
                Text('${consultation.durationMinutes} min'),
              ],
            ),
            SizedBox(height: 4),
            Chip(
              label: Text(
                consultation.statusLabel,
                style: TextStyle(fontSize: 12),
              ),
              backgroundColor: consultation.statusColor.withOpacity(0.2),
              padding: EdgeInsets.symmetric(horizontal: 8, vertical: 0),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ],
        ),
        trailing: PopupMenuButton(
          itemBuilder: (context) => [
            if (consultation.status == 'scheduled')
              PopupMenuItem(
                child: Text('Confirm'),
                value: 'confirm',
              ),
            if (consultation.status == 'confirmed')
              PopupMenuItem(
                child: Text('Complete'),
                value: 'complete',
              ),
            PopupMenuItem(
              child: Text('Mark No-Show'),
              value: 'no_show',
            ),
            PopupMenuItem(
              child: Text('Cancel'),
              value: 'cancel',
            ),
            PopupMenuItem(
              child: Text('Delete', style: TextStyle(color: Colors.red)),
              value: 'delete',
            ),
          ],
          onSelected: (value) => _handleAction(consultation, value as String),
        ),
        onTap: () => _navigateToDetails(consultation),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.calendar_today, size: 64, color: Colors.grey),
          SizedBox(height: 16),
          Text('No consultations scheduled'),
          SizedBox(height: 8),
          ElevatedButton(
            onPressed: () => _navigateToCreateConsultation(),
            child: Text('Schedule Consultation'),
          ),
        ],
      ),
    );
  }

  Future<void> _handleAction(Consultation consultation, String action) async {
    try {
      switch (action) {
        case 'confirm':
          await _service.confirmConsultation(consultation.id);
          break;
        case 'complete':
          await _service.completeConsultation(consultation.id);
          break;
        case 'no_show':
          await _service.markNoShow(consultation.id);
          break;
        case 'cancel':
          await _service.cancelConsultation(consultation.id);
          break;
        case 'delete':
          final confirm = await _showDeleteConfirmation();
          if (confirm == true) {
            await _service.deleteConsultation(consultation.id);
          } else {
            return;
          }
          break;
      }
      _loadConsultations();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Consultation updated')),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }

  String _getMonthAbbr(int month) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return months[month - 1];
  }

  void _showFilterDialog() {
    // Implement filter dialog
  }

  Future<bool?> _showDeleteConfirmation() async {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete Consultation?'),
        content: Text('This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  void _navigateToCreateConsultation() {
    // Navigate to create screen
  }

  void _navigateToDetails(Consultation consultation) {
    // Navigate to details screen
  }
}
```

### Step 4: Create Consultation Form

```dart
// lib/screens/consultations/create_consultation_screen.dart
import 'package:flutter/material.dart';
import '../../models/consultation.dart';
import '../../services/consultation_service.dart';

class CreateConsultationScreen extends StatefulWidget {
  @override
  _CreateConsultationScreenState createState() => _CreateConsultationScreenState();
}

class _CreateConsultationScreenState extends State<CreateConsultationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _notesController = TextEditingController();
  
  DateTime _selectedDate = DateTime.now();
  TimeOfDay _selectedTime = TimeOfDay.now();
  int _duration = 30;

  bool _saving = false;

  Future<void> _saveConsultation() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _saving = true);

    final consultation = Consultation(
      id: 0, // Will be set by backend
      shop: 0, // Will be set by backend
      customerName: _nameController.text,
      customerEmail: _emailController.text,
      customerPhone: _phoneController.text.isEmpty ? null : _phoneController.text,
      date: _selectedDate,
      time: _selectedTime,
      durationMinutes: _duration,
      status: 'scheduled',
      notes: _notesController.text,
      designReferenceImages: [],
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );

    try {
      final service = ConsultationService(dio); // Your Dio instance
      await service.createConsultation(consultation);
      
      Navigator.pop(context, true); // Return true to indicate success
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Consultation scheduled successfully')),
      );
    } catch (e) {
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Schedule Consultation'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: EdgeInsets.all(16),
          children: [
            // Customer Name
            TextFormField(
              controller: _nameController,
              decoration: InputDecoration(
                labelText: 'Customer Name *',
                prefixIcon: Icon(Icons.person),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return 'Please enter customer name';
                }
                return null;
              },
            ),
            SizedBox(height: 16),

            // Customer Email
            TextFormField(
              controller: _emailController,
              decoration: InputDecoration(
                labelText: 'Email *',
                prefixIcon: Icon(Icons.email),
              ),
              keyboardType: TextInputType.emailAddress,
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return 'Please enter email';
                }
                if (!value.contains('@')) {
                  return 'Please enter valid email';
                }
                return null;
              },
            ),
            SizedBox(height: 16),

            // Phone (optional)
            TextFormField(
              controller: _phoneController,
              decoration: InputDecoration(
                labelText: 'Phone (optional)',
                prefixIcon: Icon(Icons.phone),
              ),
              keyboardType: TextInputType.phone,
            ),
            SizedBox(height: 24),

            // Date Picker
            ListTile(
              leading: Icon(Icons.calendar_today),
              title: Text('Date'),
              subtitle: Text(
                '${_selectedDate.month}/${_selectedDate.day}/${_selectedDate.year}',
              ),
              trailing: Icon(Icons.arrow_forward_ios, size: 16),
              onTap: () async {
                final date = await showDatePicker(
                  context: context,
                  initialDate: _selectedDate,
                  firstDate: DateTime.now(),
                  lastDate: DateTime.now().add(Duration(days: 365)),
                );
                if (date != null) {
                  setState(() => _selectedDate = date);
                }
              },
            ),

            // Time Picker
            ListTile(
              leading: Icon(Icons.access_time),
              title: Text('Time'),
              subtitle: Text(_selectedTime.format(context)),
              trailing: Icon(Icons.arrow_forward_ios, size: 16),
              onTap: () async {
                final time = await showTimePicker(
                  context: context,
                  initialTime: _selectedTime,
                );
                if (time != null) {
                  setState(() => _selectedTime = time);
                }
              },
            ),

            // Duration
            ListTile(
              leading: Icon(Icons.timer),
              title: Text('Duration'),
              subtitle: Text('$_duration minutes'),
              trailing: DropdownButton<int>(
                value: _duration,
                items: [15, 30, 45, 60, 90, 120]
                    .map((min) => DropdownMenuItem(
                          value: min,
                          child: Text('$min min'),
                        ))
                    .toList(),
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _duration = value);
                  }
                },
              ),
            ),
            SizedBox(height: 16),

            // Notes
            TextFormField(
              controller: _notesController,
              decoration: InputDecoration(
                labelText: 'Notes',
                prefixIcon: Icon(Icons.note),
                hintText: 'Design ideas, preferences, etc.',
              ),
              maxLines: 3,
            ),
            SizedBox(height: 32),

            // Save Button
            ElevatedButton(
              onPressed: _saving ? null : _saveConsultation,
              child: _saving
                  ? CircularProgressIndicator(color: Colors.white)
                  : Text('Schedule Consultation'),
              style: ElevatedButton.styleFrom(
                padding: EdgeInsets.symmetric(vertical: 16),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

---

## ✅ Integration Checklist

- [ ] Add `Consultation` model to your models
- [ ] Create `ConsultationService` with Dio instance
- [ ] Create consultation list screen
- [ ] Create consultation form screen
- [ ] Add navigation routes
- [ ] Test create consultation
- [ ] Test list with filters
- [ ] Test status transitions (confirm, complete, cancel)
- [ ] Test delete functionality
- [ ] Add to Tattoo Artist dashboard

---

## 🎨 UI/UX Recommendations

1. **Calendar View**: Consider using a calendar widget (e.g., `table_calendar` package) for better visualization
2. **Push Notifications**: Send reminders 24 hours before consultation
3. **Design Upload**: Allow customers to upload reference images during booking
4. **Conflict Detection**: Check for time slot conflicts before creating
5. **Past Consultations**: Show history with completion notes

---

## 🧪 Testing

```dart
// Example test cases
void main() {
  group('Consultation Model', () {
    test('fromJson creates valid object', () {
      final json = {
        'id': 1,
        'shop': 7,
        'customer_name': 'Test User',
        'customer_email': 'test@example.com',
        'date': '2025-12-01',
        'time': '14:30:00',
        'duration_minutes': 30,
        'status': 'scheduled',
        // ... other fields
      };
      
      final consultation = Consultation.fromJson(json);
      
      expect(consultation.id, 1);
      expect(consultation.customerName, 'Test User');
      expect(consultation.time.hour, 14);
      expect(consultation.time.minute, 30);
    });
  });
}
```

---

## 📝 Notes

- All times are in 24-hour format from backend, convert to 12-hour for display
- Status field is lowercase with underscores (no_show, not "No Show")
- `design_reference_images` is a JSON array of URLs
- Backend auto-assigns shop based on authenticated user

---

## 🆘 Troubleshooting

**Error: "Unique constraint violation"**
- A consultation already exists for that shop/date/time combination
- Check for conflicts before creating

**Error: "Invalid time format"**
- Ensure time is sent as "HH:MM:SS" (e.g., "14:30:00")

**Empty list returned**
- Check if shop has any consultations
- Verify date filters aren't excluding all results
- Check authentication token

---

## 🚀 Ready to Implement!

All backend endpoints are live and tested. Follow this guide to integrate Consultation Calendar into your Flutter app!
