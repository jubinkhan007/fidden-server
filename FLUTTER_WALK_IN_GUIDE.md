# Flutter Walk-In Queue Integration Guide

Complete guide for integrating the Walk-In Queue backend with the Flutter app.

---

## API Endpoints

Base URL: `https://phase2.fidden.io`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/walk-in/` | List today's queue |
| `POST` | `/api/walk-in/` | Add customer to queue |
| `PATCH` | `/api/walk-in/{id}/` | Update entry |
| `DELETE` | `/api/walk-in/{id}/` | Remove from queue |
| `POST` | `/api/walk-in/{id}/start/` | Start service |
| `POST` | `/api/walk-in/{id}/complete/` | Complete with payment |
| `POST` | `/api/walk-in/{id}/no_show/` | Mark as no-show |
| `GET` | `/api/walk-in/stats/` | Get queue stats |

---

## 1. List Queue (GET /api/walk-in/)

**Request:**
```dart
final response = await api.get('/api/walk-in/');
// Optional filters
final response = await api.get('/api/walk-in/?status=waiting');
final response = await api.get('/api/walk-in/?service_niche=tattoo_artist');
```

**Response:**
```json
[
  {
    "id": 1,
    "shop": 1,
    "service": 3,
    "service_name": "Tattoo",
    "service_price": "175.00",
    "customer_name": "John Doe",
    "customer_phone": "555-1234",
    "customer_email": "",
    "user": null,
    "position": 1,
    "estimated_wait_minutes": 15,
    "status": "waiting",
    "wait_time_minutes": 10,
    "notes": "",
    "joined_at": "2026-01-02T14:30:00Z",
    "called_at": null,
    "completed_at": null,
    "slot_booking": null,
    "amount_paid": "0.00",
    "tips_amount": "0.00",
    "payment_method": null,
    "service_niche": "tattoo_artist"
  }
]
```

---

## 2. Add to Queue (POST /api/walk-in/)

**Request:**
```dart
final response = await api.post('/api/walk-in/', data: {
  'customer_name': 'John Doe',
  'customer_phone': '555-1234',  // optional
  'customer_email': 'john@example.com',  // optional
  'service': 3,  // service ID (optional)
  'notes': 'First time customer',  // optional
});
```

**Response:**
```json
{
  "id": 1,
  "position": 1,  // Auto-assigned (resets daily)
  "status": "waiting",
  "service_niche": "tattoo_artist",  // Auto-derived from service category
  ...
}
```

---

## 3. Start Service (POST /api/walk-in/{id}/start/)

Call this when you start serving the customer.

**Request:**
```dart
final response = await api.post('/api/walk-in/1/start/');
```

**Response:**
```json
{
  "id": 1,
  "status": "in_service",
  "called_at": "2026-01-02T14:45:00Z",
  ...
}
```

---

## 4. Complete with Payment (POST /api/walk-in/{id}/complete/)

**This is the checkout endpoint.** Creates SlotBooking, Payment, and TransactionLog.

**Request:**
```dart
final response = await api.post('/api/walk-in/1/complete/', data: {
  'payment_method': 'cash',  // 'cash', 'card', or 'other'
  'amount_paid': 175.00,
  'tips_amount': 20.00,  // optional, default 0
});
```

**Response:**
```json
{
  "id": 1,
  "status": "completed",
  "completed_at": "2026-01-02T15:30:00Z",
  "slot_booking": 123,  // ← Created SlotBooking ID
  "amount_paid": "175.00",
  "tips_amount": "20.00",
  "payment_method": "cash",
  ...
}
```

**What happens on backend:**
1. ✅ Creates `SlotBooking` with `is_walk_in=True`
2. ✅ Creates `Payment` record
3. ✅ Creates `TransactionLog` entry
4. ✅ Updates `Revenue` table
5. ✅ Appears in dashboard stats

---

## 5. Mark No-Show (POST /api/walk-in/{id}/no_show/)

**Request:**
```dart
final response = await api.post('/api/walk-in/1/no_show/');
```

**Response:**
```json
{
  "id": 1,
  "status": "no_show",
  ...
}
```

---

## 6. Queue Stats (GET /api/walk-in/stats/)

**Request:**
```dart
final response = await api.get('/api/walk-in/stats/');
// Filter by niche
final response = await api.get('/api/walk-in/stats/?service_niche=hairstylist');
```

**Response:**
```json
{
  "waiting": 3,
  "in_service": 1,
  "completed": 5,
  "no_show": 0,
  "total": 9
}
```

---

## 7. Update Entry (PATCH /api/walk-in/{id}/)

**Request:**
```dart
final response = await api.patch('/api/walk-in/1/', data: {
  'notes': 'Updated notes',
  'estimated_wait_minutes': 30,
});
```

---

## 8. Delete Entry (DELETE /api/walk-in/{id}/)

**Request:**
```dart
final response = await api.delete('/api/walk-in/1/');
```

---

## Flutter Model Suggestion

```dart
class WalkInEntry {
  final int id;
  final int shop;
  final int? service;
  final String? serviceName;
  final double? servicePrice;
  final String customerName;
  final String? customerPhone;
  final String? customerEmail;
  final int? user;
  final int position;
  final int estimatedWaitMinutes;
  final String status;  // 'waiting', 'in_service', 'completed', 'no_show', 'cancelled'
  final int waitTimeMinutes;
  final String? notes;
  final DateTime joinedAt;
  final DateTime? calledAt;
  final DateTime? completedAt;
  final int? slotBooking;
  final double amountPaid;
  final double tipsAmount;
  final String? paymentMethod;  // 'cash', 'card', 'other'
  final String? serviceNiche;

  WalkInEntry.fromJson(Map<String, dynamic> json)
      : id = json['id'],
        shop = json['shop'],
        service = json['service'],
        serviceName = json['service_name'],
        servicePrice = json['service_price'] != null 
            ? double.parse(json['service_price'].toString()) 
            : null,
        customerName = json['customer_name'],
        customerPhone = json['customer_phone'],
        customerEmail = json['customer_email'],
        user = json['user'],
        position = json['position'],
        estimatedWaitMinutes = json['estimated_wait_minutes'] ?? 0,
        status = json['status'],
        waitTimeMinutes = json['wait_time_minutes'] ?? 0,
        notes = json['notes'],
        joinedAt = DateTime.parse(json['joined_at']),
        calledAt = json['called_at'] != null 
            ? DateTime.parse(json['called_at']) 
            : null,
        completedAt = json['completed_at'] != null 
            ? DateTime.parse(json['completed_at']) 
            : null,
        slotBooking = json['slot_booking'],
        amountPaid = double.parse(json['amount_paid'].toString()),
        tipsAmount = double.parse(json['tips_amount'].toString()),
        paymentMethod = json['payment_method'],
        serviceNiche = json['service_niche'];
}
```

---

## Flutter Controller Suggestion

```dart
class WalkInQueueController extends GetxController {
  final RxList<WalkInEntry> queue = <WalkInEntry>[].obs;
  final Rx<WalkInStats> stats = WalkInStats().obs;
  final RxBool isLoading = false.obs;
  
  Future<void> fetchQueue({String? status, String? serviceNiche}) async {
    isLoading.value = true;
    try {
      var url = '/api/walk-in/';
      final params = <String, String>{};
      if (status != null) params['status'] = status;
      if (serviceNiche != null) params['service_niche'] = serviceNiche;
      if (params.isNotEmpty) {
        url += '?${params.entries.map((e) => '${e.key}=${e.value}').join('&')}';
      }
      
      final response = await api.get(url);
      queue.value = (response as List)
          .map((e) => WalkInEntry.fromJson(e))
          .toList();
    } finally {
      isLoading.value = false;
    }
  }
  
  Future<void> fetchStats({String? serviceNiche}) async {
    var url = '/api/walk-in/stats/';
    if (serviceNiche != null) url += '?service_niche=$serviceNiche';
    final response = await api.get(url);
    stats.value = WalkInStats.fromJson(response);
  }
  
  Future<WalkInEntry> addToQueue({
    required String customerName,
    String? customerPhone,
    int? serviceId,
    String? notes,
  }) async {
    final response = await api.post('/api/walk-in/', data: {
      'customer_name': customerName,
      if (customerPhone != null) 'customer_phone': customerPhone,
      if (serviceId != null) 'service': serviceId,
      if (notes != null) 'notes': notes,
    });
    final entry = WalkInEntry.fromJson(response);
    queue.add(entry);
    return entry;
  }
  
  Future<void> startService(int id) async {
    await api.post('/api/walk-in/$id/start/');
    await fetchQueue();
  }
  
  Future<void> complete(int id, {
    required String paymentMethod,
    required double amountPaid,
    double tipsAmount = 0,
  }) async {
    await api.post('/api/walk-in/$id/complete/', data: {
      'payment_method': paymentMethod,
      'amount_paid': amountPaid,
      'tips_amount': tipsAmount,
    });
    await fetchQueue();
    await fetchStats();
  }
  
  Future<void> markNoShow(int id) async {
    await api.post('/api/walk-in/$id/no_show/');
    await fetchQueue();
  }
}

class WalkInStats {
  final int waiting;
  final int inService;
  final int completed;
  final int noShow;
  final int total;
  
  WalkInStats({
    this.waiting = 0,
    this.inService = 0,
    this.completed = 0,
    this.noShow = 0,
    this.total = 0,
  });
  
  WalkInStats.fromJson(Map<String, dynamic> json)
      : waiting = json['waiting'] ?? 0,
        inService = json['in_service'] ?? 0,
        completed = json['completed'] ?? 0,
        noShow = json['no_show'] ?? 0,
        total = json['total'] ?? 0;
}
```

---

## UI Flow

### 1. Queue List Screen
- Show entries sorted by `position`
- Display `wait_time_minutes` for waiting entries
- Action buttons: Start Service, No Show, Complete

### 2. Add Walk-In Bottom Sheet
- Customer Name (required)
- Phone (optional)
- Select Service (optional dropdown)
- Notes (optional)
- "Add to Queue" button

### 3. Checkout Bottom Sheet
- Display service name and price
- Payment Method selector (Cash, Card, Other)
- Amount input (pre-filled with service price)
- Tips input (optional)
- "Complete" button

---

## Status Flow

```
waiting → in_service → completed
    ↓           ↓
 no_show    no_show
```

---

## Integration with Existing Checkout

After calling `/api/walk-in/{id}/complete/`, the walk-in:
- Appears in `/payments/bookings/` list
- Shows in daily revenue
- Shows in transaction history
- Counted in dashboard stats
