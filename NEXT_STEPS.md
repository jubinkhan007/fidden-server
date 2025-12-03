# Next Steps - Run These Commands

Since Docker commands are hanging in my interface, please run these directly in your Mac terminal:

## Option 1: Use the Setup Script (Easiest)

```bash
cd /Users/fionabari/fidden-backend
./setup_postgres.sh
```

## Option 2: Run Commands Manually

```bash
cd /Users/fionabari/fidden-backend

# Remove any existing container
docker rm -f fidden-postgres

# Create PostgreSQL container
docker run --name fidden-postgres \
  -e POSTGRES_PASSWORD=fidden123 \
  -e POSTGRES_DB=fidden_local \
  -p 5432:5432 \
  -d postgres:15

# Wait for PostgreSQL to start
sleep 10

# Import SQL dump (this will take 30-60 seconds)
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql

# Verify import
docker exec -it fidden-postgres psql -U postgres fidden_local -c "SELECT COUNT(*) FROM api_shop;"

# Update .env
echo 'DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local' >> .env

# Run migrations (adds Consultation table)
.venv/bin/python manage.py migrate

# Start server
.venv/bin/python manage.py runserver
```

## Then Test

Once the server is running, test the Consultation API:

```bash
# In another terminal
curl http://localhost:8000/api/consultations/
```

## If You Get Stuck

Alternative: Use SQLite instead (simpler, no Docker needed):

```bash
# Make sure DATABASE_URL is NOT set in .env
# settings.py will automatically use SQLite

# Run seed script
.venv/bin/python seed_database.py

# Run migrations
.venv/bin/python manage.py migrate

# Start server
.venv/bin/python manage.py runserver
```

---

Let me know which option you choose and if you need any help!
