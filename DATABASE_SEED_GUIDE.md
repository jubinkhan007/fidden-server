# Database Setup Guide

## ✅ Seed Files Available

Your project has **2 seed scripts**:

### 1. `seed_database.py` (NEW - COMPREHENSIVE)
**Recommended for new databases**

Creates complete test environment:
- ✅ Admin user
- ✅ 4 Shop owners (Barber, Tattoo, Nails, Fitness)
- ✅ 5 Customers
- ✅ Shops with correct niches
- ✅ Services for each shop type
- ✅ Subscription plans
- ✅ Tattoo-specific data (Portfolio, Design Requests, Consent Forms, ID Verifications)

**Usage:**
```bash
# 1. Create fresh database
python manage.py migrate

# 2. Run seed script
python seed_database.py
```

**Test Credentials Created:**
```
Admin:
  Email: admin@fidden.com
  Password: admin123

Shop Owners:
  Barber: barbershop@fidden.com / owner123
  Tattoo: tattoo@fidden.com / owner123
  Nails: nails@fidden.com / owner123
  Fitness: fitness@fidden.com / owner123

Customers:
  customer1@fidden.com through customer5@fidden.com / customer123
```

---

### 2. `create_tattoo_sample_data.py` (EXISTING - TATTOO ONLY)
**Use if you only need tattoo artist data**

Creates:
- ✅ Tattoo artist user
- ✅ Tattoo client user
- ✅ Tattoo shop
- ✅ Portfolio items
- ✅ Design requests
- ✅ Consent form templates
- ✅ ID verification requests

**Usage:**
```bash
python create_tattoo_sample_data.py
```

---

## 🚀 Quick Start (New Database)

```bash
# Step 1: Drop existing database (if needed)
# For PostgreSQL:
# dropdb fidden_db && createdb fidden_db

# Step 2: Run migrations
python manage.py migrate

# Step 3: Seed database
python seed_database.py

# Step 4: Verify
python manage.py runserver
# Visit: http://localhost:8000/admin
# Login: admin@fidden.com / admin123
```

---

## 📝 What Gets Created

### Users (11 total)
| Email | Role | Password |
|-------|------|----------|
| admin@fidden.com | Admin | admin123 |
| barbershop@fidden.com | Owner | owner123 |
| tattoo@fidden.com | Owner | owner123 |
| nails@fidden.com | Owner | owner123 |
| fitness@fidden.com | Owner | owner123 |
| customer1-5@fidden.com | Customer | customer123 |

### Shops (4 total)
| Shop Name | Owner | Niches | Services |
|-----------|-------|--------|----------|
| Bob's Barbershop | Barber | ['barber'] | 3 services |
| Ink Haven Tattoo Studio | Tattoo | ['tattoo_artist'] | 4 services |
| Glam Nails Salon | Nails | ['nail_tech', 'esthetician'] | 4 services |
| FitLife Training Center | Fitness | ['fitness_trainer'] | 0 services |

### Tattoo-Specific Data
- ✅ 3 Portfolio items
- ✅ 2 Design requests
- ✅ 1 Consent form template
- ✅ 2 ID verification requests

---

## 🔧 Troubleshooting

**Error: "Table does not exist"**
```bash
# Run migrations first
python manage.py migrate
```

**Error: "User already exists"**
```bash
# Seed script handles this automatically (get_or_create)
# It's safe to run multiple times
```

**Want to reset completely?**
```bash
# Delete database
python manage.py flush --no-input

# Re-run migrations
python manage.py migrate

# Re-seed
python seed_database.py
```

---

## ✨ Next Steps After Seeding

1. **Test Login:**
   - Visit `/admin/`
   - Login with `admin@fidden.com` / `admin123`

2. **Test API:**
   ```bash
   # Login as shop owner
   curl -X POST http://localhost:8000/accounts/login/ \
     -H "Content-Type: application/json" \
     -d '{"email":"tattoo@fidden.com","password":"owner123"}'
   
   # Get portfolio (use token from login)
   curl http://localhost:8000/api/portfolio/ \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

3. **Auto-detect Niches:**
   ```bash
   # This will set correct niches based on services
   python auto_detect_niches.py
   ```
