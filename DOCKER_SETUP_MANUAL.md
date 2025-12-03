# Docker PostgreSQL Setup - Manual Steps

## Issue Encountered
Docker Desktop had an I/O error. Here's what to do:

## Solution: Restart Docker Desktop

**Step 1: Restart Docker**
1. Click the Docker whale icon in your Mac menu bar
2. Select "Quit Docker Desktop"
3. Wait 10 seconds
4. Open Docker Desktop again
5. Wait for it to fully start

**Step 2: Create PostgreSQL Container**
```bash
# Remove any existing container
docker rm -f fidden-postgres

# Create new PostgreSQL container
docker run --name fidden-postgres \
  -e POSTGRES_PASSWORD=fidden123 \
  -e POSTGRES_DB=fidden_local \
  -p 5432:5432 \
  -d postgres:15

# Wait for PostgreSQL to initialize
sleep 10

# Verify it's running
docker ps | grep fidden-postgres
```

**Step 3: Import SQL Dump**
```bash
# Import your data (this may take 30-60 seconds)
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql

# Verify import
docker exec -it fidden-postgres psql -U postgres fidden_local -c "\dt"
docker exec -it fidden-postgres psql -U postgres fidden_local -c "SELECT COUNT(*) FROM api_shop;"
```

**Step 4: Update .env**
```bash
# Add to .env file
echo 'DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local' >> .env
```

**Step 5: Run Migrations**
```bash
# Apply Consultation migration
.venv/bin/python manage.py migrate

# Verify
.venv/bin/python manage.py showmigrations api
```

**Step 6: Start Server**
```bash
.venv/bin/python manage.py runserver
```

---

## Quick One-Liner (After Docker Restarts)

```bash
docker run --name fidden-postgres -e POSTGRES_PASSWORD=fidden123 -e POSTGRES_DB=fidden_local -p 5432:5432 -d postgres:15 && \
sleep 10 && \
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql && \
echo 'DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local' >> .env && \
.venv/bin/python manage.py migrate && \
.venv/bin/python manage.py runserver
```

---

## Verification

After everything is set up, verify:

```bash
# Check Docker container is running
docker ps

# Check database has data
docker exec -it fidden-postgres psql -U postgres fidden_local -c "SELECT COUNT(*) FROM api_shop;"

# Test Django database connection
.venv/bin/python manage.py dbshell
```

---

## If Still Having Issues

Alternative: Use SQLite (simpler, no Docker needed)

```bash
# Comment out DATABASE_URL in .env
# Django will automatically use db.sqlite3

# Run seed script instead
.venv/bin/python seed_database.py

# Start server
.venv/bin/python manage.py runserver
```
