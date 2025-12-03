# Docker PostgreSQL Setup - Quick Guide

## Step 1: Start Docker Desktop

**You need to start Docker first:**

1. Open Docker Desktop application
2. Wait for Docker to start (whale icon in menu bar should be active)
3. Verify Docker is running:
   ```bash
   docker --version
   docker ps
   ```

---

## Step 2: Create PostgreSQL Container

Once Docker is running, execute these commands:

```bash
# 1. Create and start PostgreSQL container
docker run --name fidden-postgres \
  -e POSTGRES_PASSWORD=fidden123 \
  -e POSTGRES_DB=fidden_local \
  -p 5432:5432 \
  -d postgres:15

# 2. Wait 5 seconds for PostgreSQL to initialize
sleep 5

# 3. Import your SQL dump
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql

# 4. Verify import worked
docker exec -it fidden-postgres psql -U postgres fidden_local -c "SELECT COUNT(*) FROM api_shop;"
```

---

## Step 3: Update Environment Variables

Create or update `.env.local`:

```bash
# Add this line
DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local
```

---

## Step 4: Run Migrations & Start Server

```bash
# Run migrations (to add Consultation table)
.venv/bin/python manage.py migrate

# Start Django development server
.venv/bin/python manage.py runserver
```

---

## Useful Docker Commands

```bash
# Stop the database
docker stop fidden-postgres

# Start the database
docker start fidden-postgres

# View database logs
docker logs fidden-postgres

# Connect to database
docker exec -it fidden-postgres psql -U postgres fidden_local

# Remove container (if you need to start over)
docker rm -f fidden-postgres
```

---

## Troubleshooting

**Error: "Cannot connect to Docker daemon"**
- Solution: Open Docker Desktop and wait for it to start

**Error: "Container name already in use"**
- Solution: Remove old container first:
  ```bash
  docker rm -f fidden-postgres
  ```

**Error: "Port 5432 already in use"**
- Solution: Stop Homebrew PostgreSQL:
  ```bash
  brew services stop postgresql@15
  ```

**Database import takes long**
- This is normal for a 3.7MB SQL file
- It may take 30-60 seconds depending on data complexity

---

## After Setup

Once everything is imported, you'll have:
- ✅ Full production database locally
- ✅ All users, shops, services
- ✅ All bookings and reviews
- ✅ Ready to test Consultation Calendar feature

Then you can run the migration to add the new Consultation table!
