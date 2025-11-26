# Flutter Implementation Guide: Real-time Slots & Add-on Services

This guide outlines the necessary changes in the Flutter application to support **Real-time Slot Generation** and **Add-on Services**. The backend has already been updated to support these features.

## 1. Real-time Slot Generation

### Overview
The backend now automatically regenerates slots whenever a shop owner updates their business hours or closed days. This means the API always returns the most up-to-date availability.

### Flutter Implementation
*   **No complex logic required:** You do not need to implement any complex slot calculation logic on the client side.
*   **Refresh Strategy:** Ensure that the **Slot Selection Screen** fetches the slots from the API (`GET /api/shops/{shop_id}/slots/`) *every time* the user enters the screen or changes the date.
    *   *Avoid aggressive caching* of slot data to ensure the user sees the latest changes immediately.
    *   If you are using a state management solution (Riverpod/Bloc/Provider), ensure the slot provider invalidates its cache on screen focus.

---

## 2. Add-on Services

### Overview
Users can now select additional services ("Add-ons") along with their primary service. This extends the booking duration and increases the total price.

### API Changes

#### A. Booking Endpoint (`POST /api/bookings/`)
The `SlotBookingSerializer` now accepts an optional list of add-on service IDs.

**Request Body:**
```json
{
  "slot_id": 123,
  "add_on_ids": [45, 46]  // List of Service IDs to add
}
```

**Response:**
The created booking object will have the *extended* `end_time` calculated by the backend.

#### B. Payment Intent Endpoint
The payment calculation logic on the backend now automatically includes the price of all selected add-ons. No changes are needed in the payload sent to `CreatePaymentIntentView`, but the **UI** must display the correct total before payment.

### Flutter Implementation Steps

#### Step 1: Fetch Available Add-ons
*   On the **Booking/Slot Selection Screen**, fetch the list of services for the current shop.
*   **Filter:** Exclude the *primary* service currently being booked from this list to show valid "Add-ons".
*   **UI:** Display these services as a selectable list (e.g., "Add these to your appointment?"). Allow multi-selection.

#### Step 2: Update UI State (Price & Duration)
*   Maintain a state of `selectedAddOns` (List<Service>).
*   **Calculate Display Values:**
    *   `Total Duration` = `PrimaryService.duration` + `Sum(AddOn.duration)`
    *   `Total Price` = `PrimaryService.price` + `Sum(AddOn.price)`
*   Update the "Book Now" summary to reflect these totals so the user knows what they are paying for and how long it will take.

#### Step 3: Create Booking with Add-ons
*   When the user confirms the slot, update the API call to `createBooking` (or equivalent).
*   Include the `add_on_ids` field in the payload:
    ```dart
    final payload = {
      "slot_id": selectedSlot.id,
      "add_on_ids": selectedAddOns.map((s) => s.id).toList(),
    };
    // POST to /api/bookings/
    ```

#### Step 4: Handle Validation Errors
*   The backend validates that the selected slot has enough capacity and time for the *total duration*.
*   If the extended duration overlaps with another booking or exceeds shop hours, the API will return a `400 Bad Request` with a message like:
    > "You already have a booking that overlaps this slot (including add-ons)."
*   **Action:** Display this error to the user and prompt them to select a different slot or remove add-ons.

### Summary Checklist
- [ ] **Slot Screen:** Refresh slots on entry (don't over-cache).
- [ ] **Booking Flow:** Fetch other shop services to display as "Add-ons".
- [ ] **UI:** Allow multi-selection of add-ons.
- [ ] **UI:** Dynamically update "Total Price" and "Total Duration" labels.
- [ ] **API:** Send `add_on_ids` in the booking creation request.
- [ ] **Error Handling:** specific handling for overlap errors due to extended duration.
