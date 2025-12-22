# Flutter Implementation Prompt: Tattoo Portfolio & Design Request

## Context

We need to implement two client-facing features for the tattoo artist niche:
1. **View Shop Portfolio** - Clients can browse tattoo artist's work before booking
2. **Submit Design Request** - Clients can submit tattoo ideas/references to the artist

Before implementing, please create a plan on how you think best to implement the UI and organize the flow to incorporate these features into the existing app.

---

## API Endpoints

### 1. View Shop Portfolio (Public)

**GET** `/api/shops/{shop_id}/gallery/`

No authentication required.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter by category (e.g., `tattoo`, `flash`, `custom`) |

**Response:**
```json
[
  {
    "id": 1,
    "image_url": "https://phase2.fidden.io/media/gallery/tattoo1.jpg",
    "thumbnail_url": "https://phase2.fidden.io/media/gallery/thumbs/tattoo1.jpg",
    "caption": "Traditional Japanese Dragon",
    "service": 5,
    "service_name": "Large Tattoo",
    "category_tag": "tattoo",
    "created_at": "2025-12-15T10:00:00Z"
  },
  {
    "id": 2,
    "image_url": "https://phase2.fidden.io/media/gallery/tattoo2.jpg",
    "thumbnail_url": "https://phase2.fidden.io/media/gallery/thumbs/tattoo2.jpg",
    "caption": "Geometric Mandala",
    "service": 6,
    "service_name": "Medium Tattoo",
    "category_tag": "tattoo",
    "created_at": "2025-12-14T10:00:00Z"
  }
]
```

---

### 2. Submit Design Request (Client - Auth Required)

**POST** `/api/design-requests/`

Requires authentication.

**Request Body:**
```json
{
  "shop": 5,
  "booking": 123,
  "description": "I want a traditional Japanese dragon on my back. Looking for bold lines and vibrant colors. Reference images attached.",
  "placement": "Full back",
  "size_approx": "Large (12+ inches)"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shop` | integer | **Yes** | Shop ID |
| `booking` | integer | No | Link to existing booking (optional) |
| `description` | string | **Yes** | Detailed description of desired tattoo |
| `placement` | string | No | Body placement (e.g., "Forearm", "Back", "Chest") |
| `size_approx` | string | No | Approximate size (e.g., "Small", "Medium", "Large") |

**Response:**
```json
{
  "id": 1,
  "shop": 5,
  "user": 42,
  "user_name": "John Doe",
  "user_email": "john@email.com",
  "booking": 123,
  "description": "I want a traditional Japanese dragon on my back...",
  "placement": "Full back",
  "size_approx": "Large (12+ inches)",
  "status": "pending",
  "images": [],
  "created_at": "2025-12-19T10:00:00Z",
  "updated_at": "2025-12-19T10:00:00Z"
}
```

---

### 3. View My Design Requests (Client - Auth Required)

**GET** `/api/design-requests/`

Returns the authenticated client's design requests.

**Response:**
```json
[
  {
    "id": 1,
    "shop": 5,
    "user": 42,
    "user_name": "John Doe",
    "user_email": "john@email.com",
    "booking": 123,
    "description": "Japanese dragon tattoo",
    "placement": "Full back",
    "size_approx": "Large",
    "status": "approved",
    "images": [
      {
        "id": 1,
        "image": "https://phase2.fidden.io/media/design_requests/ref1.jpg"
      }
    ],
    "created_at": "2025-12-15T10:00:00Z",
    "updated_at": "2025-12-18T14:30:00Z"
  }
]
```

---

### 4. Get Single Design Request

**GET** `/api/design-requests/{id}/`

**Response:** Same as single object in list above.

---

### 5. Update Design Request (Client)

**PATCH** `/api/design-requests/{id}/`

Client can update their pending requests.

**Request Body:**
```json
{
  "description": "Updated description with more details",
  "placement": "Upper back"
}
```

---

### 6. Delete Design Request (Client)

**DELETE** `/api/design-requests/{id}/`

**Response:** `204 No Content`

---

## Status Values

| Status | Description | UI Indication |
|--------|-------------|---------------|
| `pending` | Waiting for artist review | Yellow/Orange badge |
| `approved` | Design approved | Green badge |
| `rejected` | Design rejected | Red badge |
| `completed` | Tattoo completed | Blue/Gray badge |

---

## Implementation Requirements

### Portfolio Screen
- Grid/masonry layout for portfolio images
- Tap to view full image with caption
- Filter by category (optional)
- Link to book appointment from portfolio item
- Should be accessible from Shop Details screen

### Design Request Flow
- Form with description, placement picker, size picker
- Option to attach reference images (future)
- Link to existing booking (optional)
- Show submission success with status
- List of user's design requests with status

### Navigation Suggestions
- Add "Portfolio" tab/button on Shop Details screen
- Add "My Design Requests" in user profile or bookings section
- Add "Submit Design Request" CTA on booking confirmation or shop page

---

## Questions to Answer in Your Plan

1. Where should the Portfolio be accessible from? (Shop Details, Service Selection, etc.)
2. Where should "Submit Design Request" be triggered? (Before booking, after booking, standalone)
3. How to handle image attachments for design requests? (Current backend supports image model, need upload endpoint)
4. Should design requests be linked to bookings or standalone?
5. How to notify clients when status changes? (Push notification, in-app)

---

## API Base URL

```
https://phase2.fidden.io
```

All endpoints require the standard Authorization header for authenticated requests:
```
Authorization: Bearer {access_token}
```
