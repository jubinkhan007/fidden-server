# Fidden Pay - Flutter Integration Guide

## Backend Changes Summary

### New Payment Model Fields
- `deposit_status`: 'held' | 'credited' | 'forfeited'
- `service_price`: Full service price for commission calculation
- `tip_percent`, `tip_base`, `tip_option_selected`: Tip tracking
- `final_charge_amount`: Remaining + tip at checkout

### Commission Change
**Commission = 10% of full service price, deducted from deposit**
- $100 service, $30 deposit → $10 commission → Shop receives $20 from deposit
- At checkout: Client pays $70 + tip (no additional commission)

---

## API Endpoints

### 1. Deposit Payment (Existing - Modified)
```
POST /payments/payment-intent/{slot_id}/
```
- Unchanged API, but now:
  - Commission calculated on full `service_price`
  - Payment record stores `deposit_status='held'`

---

### 2. Initiate Checkout (NEW - Owner App)
```
POST /payments/initiate-checkout/{booking_id}/
Authorization: Bearer {owner_token}
```

**Response:**
```json
{
  "booking_id": 123,
  "service_price": 100.00,
  "deposit_paid": 30.00,
  "remaining_amount": 70.00,
  "tip_base": 100.00,
  "tip_options": [
    {"option": "10", "amount": 10.00},
    {"option": "15", "amount": 15.00},
    {"option": "20", "amount": 20.00}
  ],
  "shop_name": "All-in-one Shop",
  "service_title": "HairCut"
}
```

---

### 3. Complete Checkout (NEW - Customer App)
```
POST /payments/complete-checkout/{booking_id}/
Authorization: Bearer {customer_token}
Content-Type: application/json

{
  "tip_option": "15",      // "10", "15", "20", "custom", or "0"
  "tip_amount": 15.00      // Required if tip_option is "custom"
}
```

**Response:**
```json
{
  "client_secret": "pi_xxx_secret_xxx",
  "payment_intent_id": "pi_xxx",
  "ephemeral_key": "ek_xxx",
  "customer_id": "cus_xxx",
  "final_amount": 85.00,
  "remaining_amount": 70.00,
  "tip_amount": 15.00
}
```

---

## Flutter Implementation

### Owner App - Checkout Button Flow

```dart
// 1. Owner taps "Checkout" on active booking
Future<void> initiateCheckout(int bookingId) async {
  final response = await dio.post(
    '/payments/initiate-checkout/$bookingId/',
  );
  
  if (response.statusCode == 200) {
    final data = response.data;
    // Navigate to checkout screen or show notification
    // Customer will receive checkout request
  }
}
```

### Customer App - Tip Selection & Payment

```dart
class CheckoutScreen extends StatefulWidget {
  final int bookingId;
  final double servicePrice;
  final double remainingAmount;
  final List<TipOption> tipOptions;
  
  // ...
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  String selectedTipOption = '15';
  double? customTipAmount;
  
  double get tipAmount {
    if (selectedTipOption == 'custom') {
      return customTipAmount ?? 0;
    }
    return widget.tipOptions
        .firstWhere((t) => t.option == selectedTipOption)
        .amount;
  }
  
  double get totalDue => widget.remainingAmount + tipAmount;
  
  Future<void> completeCheckout() async {
    final response = await dio.post(
      '/payments/complete-checkout/${widget.bookingId}/',
      data: {
        'tip_option': selectedTipOption,
        'tip_amount': selectedTipOption == 'custom' ? customTipAmount : null,
      },
    );
    
    if (response.statusCode == 200) {
      final data = response.data;
      
      // Use Stripe SDK to confirm payment
      await Stripe.instance.confirmPayment(
        paymentIntentClientSecret: data['client_secret'],
        data: PaymentMethodParams.card(
          paymentMethodData: PaymentMethodData(),
        ),
      );
      
      // Show success
      Navigator.pop(context, true);
    }
  }
}
```

---

## Checkout UI Design

```
┌─────────────────────────────────────┐
│         Complete Checkout           │
├─────────────────────────────────────┤
│  Service: HairCut                   │
│  Total: $100.00                     │
│  Deposit Paid: -$30.00              │
│  Remaining: $70.00                  │
│                                     │
│  Add a tip:                         │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌─────┐│
│  │ 10%  │ │ 15%  │ │ 20%  │ │Custom│
│  │ $10  │ │ $15  │ │ $20  │ │     ││
│  └──────┘ └──────┘ └──────┘ └─────┘│
│                                     │
│  Total Due: $85.00                  │
│                                     │
│  ┌─────────────────────────────┐    │
│  │        Pay $85.00           │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

---

## Deposit Status Handling

```dart
enum DepositStatus { held, credited, forfeited }

class BookingPayment {
  final DepositStatus depositStatus;
  final double depositAmount;
  final double remainingAmount;
  
  bool get canCheckout => depositStatus == DepositStatus.held;
  bool get isCompleted => depositStatus == DepositStatus.credited;
  bool get isForfeited => depositStatus == DepositStatus.forfeited;
}
```

---

## Pro Earnings Report (Owner App)

### 4. Shop Earnings Report (NEW - Owner App)
```
GET /payments/shop-earnings/{shop_id}/?period=month
Authorization: Bearer {owner_token}
```

**Query Parameters:**
- `period`: `day` | `week` | `month` (default: month)

**Response:**
```json
{
  "shop_id": 1,
  "shop_name": "All-in-one Shop",
  "period": "month",
  "start_date": "2025-12-01T00:00:00Z",
  "end_date": "2025-12-10T15:30:00Z",
  "earnings": {
    "service_revenue": 500.00,
    "tips_total": 75.00,
    "gross_revenue": 575.00,
    "commission": 50.00,
    "net_payout": 525.00
  },
  "deposits": {
    "credited": 150.00,
    "forfeited": 30.00
  },
  "bookings": {
    "total": 10,
    "completed": 9,
    "forfeited": 1
  }
}
```

### Flutter Implementation - Earnings Dashboard

```dart
class EarningsScreen extends StatefulWidget {
  final int shopId;
  // ...
}

class _EarningsScreenState extends State<EarningsScreen> {
  String selectedPeriod = 'month';
  Map<String, dynamic>? earnings;
  
  Future<void> fetchEarnings() async {
    final response = await dio.get(
      '/payments/shop-earnings/${widget.shopId}/',
      queryParameters: {'period': selectedPeriod},
    );
    
    if (response.statusCode == 200) {
      setState(() => earnings = response.data);
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Period selector
        SegmentedButton(
          segments: ['day', 'week', 'month'],
          selected: selectedPeriod,
          onChanged: (period) {
            selectedPeriod = period;
            fetchEarnings();
          },
        ),
        
        // Earnings cards
        if (earnings != null) ...[
          Text('Net Payout: \$${earnings!['earnings']['net_payout']}'),
          Text('Tips: \$${earnings!['earnings']['tips_total']}'),
          Text('Commission: \$${earnings!['earnings']['commission']}'),
          Text('Bookings: ${earnings!['bookings']['total']}'),
        ],
      ],
    );
  }
}
```

---

## Error Handling

| Status Code | Error | Action |
|-------------|-------|--------|
| 403 | Not authorized | User mismatch |
| 400 | Already checked out | Show message |
| 400 | Deposit forfeited | Show no-show message |
