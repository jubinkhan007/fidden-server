# Tattoo Artist Administration Guide

## ✅ YES, You Can Use Django Admin!

Since you deployed the `phase2` branch on a separate Render web service, you should have access to the Django admin panel.

---

## Step-by-Step Instructions

### 1. Access Django Admin

**URL Format:**
```
https://YOUR-PHASE2-SERVICE-NAME.onrender.com/admin/
```

Replace `YOUR-PHASE2-SERVICE-NAME` with your actual service name from Render.

### 2. Login Credentials

Use your Django superuser credentials. If you don't have a superuser yet, create one:

**On Render Shell:**
```bash
python manage.py createsuperuser
```

Follow the prompts to create username, email, and password.

### 3. Navigate to Shop Model

1. After login, find **"Shops"** in the admin panel
2. Click on **"Shop"**  
3. Find your test shop (search by name or owner email)
4. Click to edit

### 4. Set the Niche Field

**IMPORTANT:** You need to add the `niche` field to the admin interface first!

The `niche` field exists in the model but isn't visible in the admin panel yet. Here's how to fix it:

---

## Quick Fix: Add Niche to Admin

I need to update `api/admin.py` to include the `niche` field. Let me do that now.

**Current Status:**
- ❌ Niche field **NOT** visible in Shop admin
- ❌ Tattoo models **NOT** registered in admin

**What Needs to be Done:**
1. Add `niche` to ShopAdmin fieldsets
2. Register tattoo models (Portfolio, DesignRequest, etc.) in admin
3. Redeploy phase2

---

## Alternative: Manual Database Update

If you need to set the niche **right now** before the admin fix, you can use the Render shell:

```bash
python manage.py shell
```

Then run:
```python
from api.models import Shop

# Find your shop (replace with your shop ID or email)
shop = Shop.objects.get(id=YOUR_SHOP_ID)
# OR
shop = Shop.objects.get(owner__email="your-email@example.com")

# Set niche
shop.niche = 'tattoo_artist'
shop.save()

print(f"✅ Updated {shop.name} to niche: {shop.niche}")
```

---

## Next Step

Would you like me to:
1. **Update the admin.py** to include niche field and tattoo models?
2. **Give you the shell commands** to manually update your shop?
3. **Both** - update admin and provide shell commands for immediate testing?

Let me know and I'll help you get the niche set up!
