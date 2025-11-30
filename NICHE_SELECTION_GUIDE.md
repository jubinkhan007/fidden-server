# Niche Selection Guide for Django Admin

## How to Set Shop Niches

### Via Django Admin (Recommended)

1. Go to Django Admin → Shops → Select a shop
2. In "Basic Information" section, find "Selected niches"
3. Check the boxes for all service types this shop offers
4. **Important**: The order matters!
   - **First checkbox selected** = Primary Niche (drives main dashboard)
   - **Other checkboxes** = Capabilities (add extra dashboard sections)
5. Save the shop

**Example:**
- Shop offers Haircut + Facials
- Check ☑️ Barber (first)
- Check ☑️ Esthetician/Massage Therapist  
- Result: `primary_niche = "barber"`, `capabilities = ["esthetician"]`

---

### Via Management Script

Use `manage_shop_niches.py`:

```bash
# List all shops and their niches
python manage_shop_niches.py

# Update a specific shop
python manage_shop_niches.py
# Then in Python shell:
>>> update_shop_niches(shop_id=1, niches=["barber"])
>>> update_shop_niches(shop_id=2, niches=["barber", "massage_therapist"])
```

---

### Available Niches

| Code | Display Name | Dashboard Features |
|------|-------------|-------------------|
| `barber` | Barber | Today's Appointments, Daily Revenue, No-Show Alerts |
| `hairstylist` | Hairstylist/Loctician | Prep Notes, Client Gallery, Style Tags |
| `nail_tech` | Nail Tech | Style Bookings, Earnings, Moodboard |
| `tattoo_artist` | Tattoo Artist | Portfolio, Design Requests, Consent Forms |
| `makeup_artist` | Makeup Artist (MUA) | Event Bookings, Look Types, Face Charts |
| `esthetician` | Esthetician/Massage | Treatment Tracker, Health Disclosures |
| `fitness_trainer` | Fitness Trainer | Class Schedule, Client Progress |
| `other` | Other | Generic dashboard |

---

## API Response

After setting niches, the login/profile API will return:

```json
{
  "primary_niche": "barber",
  "capabilities": ["esthetician"],
  "shop_niches": ["barber", "esthetician"]
}
```

**Frontend Usage:**
- `primary_niche` → Determines Hero section of dashboard
- `capabilities` → Adds secondary dashboard sections
- Context chips: "All • Barber • Esthetician"

---

## Common Scenarios

### Single-Niche Shop (e.g., Barber Only)
- Check ☑️ Barber
- Result: `shop_niches = ["barber"]`
- Dashboard: Barber tiles only

### Multi-Niche Shop (e.g., Barber + Massage)
- Check ☑️ Barber (primary)
- Check ☑️ Esthetician/Massage Therapist
- Result: `shop_niches = ["barber", "esthetician"]`
- Dashboard: Barber tiles (hero) + Esthetician tiles (secondary)

### Changing Primary Niche
To change which niche is primary:
1. Uncheck all boxes
2. Check the NEW primary niche FIRST
3. Then check other capabilities
4. Save

---

## Troubleshooting

**Q: Flutter app shows wrong niches**
A: Check if `shop.niches` is correctly set in Django Admin. The API pulls from this field.

**Q: Which niche should be primary?**
A: The one that represents the shop's main identity. This will drive the default dashboard layout.

**Q: Can I change niches after onboarding?**
A: Yes, update anytime via Django Admin.
