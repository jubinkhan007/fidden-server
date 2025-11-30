# Auto-Niche Detection - Documentation

## Overview

Shops' niches are now **automatically detected** from their services. The system maps service categories to appropriate niches.

---

## How It Works

### 1. Category-to-Niche Mapping

The system uses keyword matching on service category names:

| Service Category Keywords | Detected Niche |
|--------------------------|----------------|
| haircut, beard, shave, barber | `barber` |
| hair, hairstyle, locs | `hairstylist` |
| nails, nail, manicure, pedicure | `nail_tech` |
| skincare, facial, waxing, skin | `esthetician` |
| massage, spa, therapy | `esthetician` |
| makeup, cosmetic | `makeup_artist` |
| tattoo, piercing, ink | `tattoo_artist` |
| fitness, training, gym, yoga | `fitness_trainer` |

### 2. Multi-Niche Detection

- Niches are sorted by **frequency** (most common service type = primary niche)
- If a shop offers 10 haircut services and 2 massage services:
  - Primary niche: `barber`
  - Capabilities: `esthetician`

### 3. Auto-Update

Niches are automatically detected when:
- Running `auto_detect_niches.py` script manually
- Can be triggered via Django Admin (future enhancement)

---

## Usage

### Manual Update (All Shops)

```bash
python auto_detect_niches.py
```

This will:
- Analyze all shops' services
- Detect niches based on category mapping
- Update `shop.niches` field
- Show before/after for each shop

### Manual Update (Single Shop)

```python
from api.models import Shop

shop = Shop.objects.get(id=1)
shop.update_niches_from_services(save=True)

print(f"Primary Niche: {shop.primary_niche}")
print(f"Capabilities: {shop.niches[1:]}")
```

### View Detection Without Saving

```python
shop = Shop.objects.get(id=1)
detected = shop.auto_detect_niches()
print(f"Would detect: {detected}")
```

---

## Examples from Latest Run

```
Shop: Nas'S Saloon
Services: 4 (Haircut, Nails, Facial, Waxing)
Old niches: ['other']
New niches: ['barber', 'nail_tech', 'esthetician']
Primary: barber
Capabilities: ['nail_tech', 'esthetician']
```

```
Shop: Test Shop  
Services: 3 (Hair Styling services)
Old niches: ['other']
New niches: ['hairstylist']
Primary: hairstylist
Capabilities: []
```

---

## API Response

After auto-detection, the login/profile API automatically returns:

```json
{
  "primary_niche": "barber",
  "capabilities": ["nail_tech", "esthetician"],
  "shop_niches": ["barber", "nail_tech", "esthetician"]
}
```

**Flutter app receives this automatically** - no changes needed on frontend!

---

## Benefits

✅ **Automatic** - No manual configuration needed  
✅ **Accurate** - Based on actual services offered  
✅ **Dynamic** - Updates when services change  
✅ **Multi-niche** - Detects all service types

---

## Future Enhancements

- Auto-update on service creation/deletion (via Django signals)
- Django Admin button to "Refresh Niches from Services"
- Weighted mapping (e.g., if shop name contains "Barber" → increase barber weight)
