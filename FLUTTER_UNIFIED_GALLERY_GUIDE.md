# Flutter Unified Portfolio Gallery Guide

## Overview

All niches share a **unified GalleryItem** model with tag-based filtering. No separate models needed for portfolio/design galleries.

---

## Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/gallery/` | Owner | Owner's gallery with filters |
| `POST /api/gallery/` | Owner | Upload new item |
| `PATCH /api/gallery/{id}/` | Owner | Update item |
| `DELETE /api/gallery/{id}/` | Owner | Delete item |
| `GET /api/shops/{id}/gallery/` | Public | Public shop gallery |

---

## Query Parameters (All Views)

| Param | Type | Example | Description |
|-------|------|---------|-------------|
| `niche` | string | `?niche=tattoo` | Filter by niche |
| `tags` | string | `?tags=bridal,glam` | Comma-separated tags |
| `category` | string | `?category=face_chart` | Filter by category_tag |
| `page` | int | `?page=2` | Pagination (public only) |

---

## Niche Values & Tags

```dart
enum GalleryNiche {
  tattoo('tattoo', ['tattoo', 'ink', 'design', 'flash', 'custom']),
  nail('nail', ['nail', 'manicure', 'pedicure', 'gel', 'acrylic', 'nail_art']),
  makeup('makeup', ['makeup', 'mua', 'face_chart', 'bridal', 'glam', 'natural']),
  hair('hair', ['hair', 'hairstyle', 'color', 'cut', 'braids', 'locs']),
  barber('barber', ['barber', 'fade', 'haircut', 'beard', 'lineup']);

  final String value;
  final List<String> tags;
  const GalleryNiche(this.value, this.tags);
}
```

---

## GalleryItem Model

```dart
class GalleryItem {
  final int id;
  final int shopId;
  final String imageUrl;
  final String? thumbnailUrl;
  final String? caption;
  final String? description;
  final int? serviceId;
  final String? categoryTag;
  final List<String> tags;
  final bool isPublic;
  final int? clientId;        // For face charts
  final String? clientName;
  final String? lookType;     // MUA: natural, glam, bridal, etc.
  final DateTime createdAt;

  GalleryItem({...});

  factory GalleryItem.fromJson(Map<String, dynamic> json) {
    return GalleryItem(
      id: json['id'],
      shopId: json['shop'],
      imageUrl: json['image'] ?? '',
      thumbnailUrl: json['thumbnail'],
      caption: json['caption'],
      description: json['description'],
      serviceId: json['service'],
      categoryTag: json['category_tag'],
      tags: List<String>.from(json['tags'] ?? []),
      isPublic: json['is_public'] ?? true,
      clientId: json['client'],
      clientName: json['client_name'],
      lookType: json['look_type'],
      createdAt: DateTime.parse(json['created_at']),
    );
  }
}
```

---

## API Response Examples

### GET `/api/gallery/?niche=tattoo`

```json
[
  {
    "id": 1,
    "shop": 5,
    "image": "https://backend.fidden.io/media/gallery/tattoo1.jpg",
    "thumbnail": "https://backend.fidden.io/media/gallery/thumbnails/tattoo1.jpg",
    "caption": "Japanese Dragon Sleeve",
    "description": "Full sleeve dragon design",
    "service": 12,
    "category_tag": "tattoo",
    "tags": ["tattoo", "japanese", "dragon", "sleeve"],
    "is_public": true,
    "client": null,
    "client_name": null,
    "look_type": "",
    "created_at": "2025-12-10T14:30:00Z"
  }
]
```

### GET `/api/gallery/?niche=makeup`

```json
[
  {
    "id": 5,
    "shop": 5,
    "image": "https://backend.fidden.io/media/gallery/bridal1.jpg",
    "thumbnail": "...",
    "caption": "Bridal Look - Sarah",
    "category_tag": "face_chart",
    "tags": ["makeup", "bridal", "glam"],
    "is_public": false,
    "client": 42,
    "client_name": "Sarah Johnson",
    "look_type": "bridal",
    "created_at": "2025-12-15T10:00:00Z"
  }
]
```

---

## Service Layer

```dart
class GalleryService {
  final Dio _dio;
  GalleryService(this._dio);

  // Owner gallery with niche filter
  Future<List<GalleryItem>> getGallery({String? niche, List<String>? tags}) async {
    final params = <String, dynamic>{};
    if (niche != null) params['niche'] = niche;
    if (tags != null) params['tags'] = tags.join(',');
    
    final response = await _dio.get('/api/gallery/', queryParameters: params);
    return (response.data as List).map((e) => GalleryItem.fromJson(e)).toList();
  }

  // Public gallery for clients
  Future<List<GalleryItem>> getPublicGallery(int shopId, {String? niche, int page = 1}) async {
    final params = <String, dynamic>{'page': page};
    if (niche != null) params['niche'] = niche;
    
    final response = await _dio.get('/api/shops/$shopId/gallery/', queryParameters: params);
    return (response.data['results'] as List).map((e) => GalleryItem.fromJson(e)).toList();
  }

  // Upload with tags
  Future<GalleryItem> uploadItem({
    required File image,
    String? caption,
    String? description,
    required String categoryTag,
    required List<String> tags,
    bool isPublic = true,
    int? clientId,
    String? lookType,
  }) async {
    final formData = FormData.fromMap({
      'image': await MultipartFile.fromFile(image.path),
      if (caption != null) 'caption': caption,
      if (description != null) 'description': description,
      'category_tag': categoryTag,
      'tags': jsonEncode(tags),
      'is_public': isPublic,
      if (clientId != null) 'client': clientId,
      if (lookType != null) 'look_type': lookType,
    });
    
    final response = await _dio.post('/api/gallery/', data: formData);
    return GalleryItem.fromJson(response.data);
  }
}
```

---

## Niche-Specific Usage

### Tattoo Artist Dashboard
```dart
// Portfolio screen
final items = await galleryService.getGallery(niche: 'tattoo');

// Upload with tattoo tags
await galleryService.uploadItem(
  image: file,
  caption: 'Japanese Dragon',
  categoryTag: 'tattoo',
  tags: ['tattoo', 'japanese', 'dragon', 'flash'],
);
```

### Nail Tech Dashboard
```dart
// Lookbook screen
final items = await galleryService.getGallery(niche: 'nail');

// Upload nail design
await galleryService.uploadItem(
  image: file,
  caption: 'Gel French Tips',
  categoryTag: 'nail',
  tags: ['nail', 'gel', 'french', 'manicure'],
);
```

### MUA Dashboard
```dart
// Face charts screen
final items = await galleryService.getGallery(
  niche: 'makeup',
  tags: ['face_chart'],
);

// Upload face chart with client link
await galleryService.uploadItem(
  image: file,
  caption: 'Bridal Look - Sarah',
  categoryTag: 'face_chart',
  tags: ['makeup', 'bridal', 'glam'],
  isPublic: false,  // Face charts are private
  clientId: 42,
  lookType: 'bridal',
);
```

### Barber Dashboard
```dart
// Portfolio screen
final items = await galleryService.getGallery(niche: 'barber');

// Upload haircut
await galleryService.uploadItem(
  image: file,
  caption: 'Low Fade with Design',
  categoryTag: 'barber',
  tags: ['barber', 'fade', 'design', 'lineup'],
);
```

---

## UI Implementation

### Reusable Gallery Grid Widget

```dart
class GalleryGridWidget extends StatelessWidget {
  final String niche;
  final Function(GalleryItem) onItemTap;
  
  // Use same widget for all niches, just pass different niche param
  Widget build(BuildContext context) {
    return FutureBuilder<List<GalleryItem>>(
      future: galleryService.getGallery(niche: niche),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return CircularProgressIndicator();
        
        return GridView.builder(
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3,
            crossAxisSpacing: 4,
            mainAxisSpacing: 4,
          ),
          itemCount: snapshot.data!.length,
          itemBuilder: (context, index) {
            final item = snapshot.data![index];
            return GestureDetector(
              onTap: () => onItemTap(item),
              child: Image.network(
                item.thumbnailUrl ?? item.imageUrl,
                fit: BoxFit.cover,
              ),
            );
          },
        );
      },
    );
  }
}
```

### Usage Per Niche

```dart
// Tattoo Portfolio Screen
GalleryGridWidget(niche: 'tattoo', onItemTap: _showTattooDetail)

// Nail Lookbook Screen
GalleryGridWidget(niche: 'nail', onItemTap: _showNailDetail)

// MUA Face Charts Screen
GalleryGridWidget(niche: 'makeup', onItemTap: _showFaceChartDetail)

// Barber Portfolio Screen
GalleryGridWidget(niche: 'barber', onItemTap: _showBarberDetail)
```

---

## Recommended Tags by Niche

| Niche | category_tag | Suggested tags |
|-------|--------------|----------------|
| Tattoo | `tattoo`, `flash`, `custom` | ink, design, sleeve, portrait, japanese, traditional, realism |
| Nail | `nail`, `nail_art`, `design` | gel, acrylic, manicure, pedicure, french, ombre, glitter |
| Makeup | `face_chart`, `makeup`, `look` | bridal, glam, natural, editorial, sfx, evening |
| Barber | `barber`, `haircut` | fade, lineup, beard, taper, design, mohawk |
| Hair | `hairstyle`, `color` | cut, braids, locs, extensions, balayage, highlights |

---

## File Structure

```
lib/features/business_owner/common/
├── data/
│   └── gallery_item_model.dart    # Shared model
├── services/
│   └── gallery_service.dart       # Shared service
└── widgets/
    ├── gallery_grid_widget.dart   # Reusable grid
    └── gallery_item_card.dart     # Reusable card
```

Each niche dashboard imports from `common/` and filters by niche.
