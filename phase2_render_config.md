# Phase2 Deployment Configuration Guide

## Required Environment Variables for Phase2

Add these to your **Render Dashboard** → **fidden-server-2** → **Environment** tab:

### 1. ALLOWED_HOSTS (CRITICAL - Fix Current Error)
```
ALLOWED_HOSTS=localhost,127.0.0.1,fidden-server-2.onrender.com
```

### 2. AWS S3 Configuration (For Images)
```
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
USE_S3=True
```

### 3. Copy All Other Variables from Main Deployment

Make sure phase2 has the same environment variables as your main deployment:

**Database:**
- `DATABASE_URL`
- `POSTGRES_HOST`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`

**Django:**
- `SECRET_KEY`
- `DEBUG=True` (for testing)

**PayPal:**
- `PAYPAL_CLIENT_ID`
- `PAYPAL_SECRET`
- `PAYPAL_BASE_URL`
- `PAYPAL_PLAN_MOMENTUM_ID`
- `PAYPAL_PLAN_ICON_ID`
- `PAYPAL_PLAN_AI_ADDON_ID`

**Stripe:**
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_ENDPOINT_SECRET`

**Email:**
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS=true`

**Redis/Celery:**
- `REDIS_URL`
- `CELERY_BROKER_URL`

**FCM (Push Notifications):**
- `FCM_SERVER_KEY`
- `FCM_SERVICE_ACCOUNT_FILE`

---

## After Adding Variables

1. Render will **automatically redeploy** phase2
2. Wait for deployment to complete (~5 minutes)
3. Test the endpoints:
   - `/admin/` (should work)
   - `/api/shop/7/` (should work)
   - `/accounts/login/` (should work)

---

## Quick Test Commands

Once deployed, test with:

```bash
# Test login
curl -X POST https://fidden-server-2.onrender.com/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"your-email","password":"your-password"}'

# Test shop endpoint
curl https://fidden-server-2.onrender.com/api/shop/7/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Setting Shop Niche (After Environment is Fixed)

### Option A: Django Admin
1. Go to `https://fidden-server-2.onrender.com/admin/`
2. Login with superuser
3. Navigate to **Shops** → Find your shop
4. Set **Niche** to `tattoo_artist`
5. Save

### Option B: Render Shell
1. Open Render shell for phase2
2. Run:
```python
python manage.py shell
from api.models import Shop
shop = Shop.objects.get(id=7)
shop.niche = 'tattoo_artist'
shop.save()
print(f"✅ {shop.name} niche: {shop.niche}")
```

---

**First Priority:** Add the `ALLOWED_HOSTS` variable to fix the immediate error!
