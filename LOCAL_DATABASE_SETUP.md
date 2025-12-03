# Local Database Setup Guide

## Setup Local PostgreSQL with SQL Dump

You have a SQL dump file (`fidden.sql`) that you can use for local testing.

### Step 1: Install PostgreSQL (if not installed)

```bash
# On macOS with Homebrew
brew install postgresql@15
brew services start postgresql@15

# Verify installation
psql --version
```

### Step 2: Create Local Database

```bash
# Create a new database called 'fidden_local'
createdb fidden_local

# Or using psql
psql postgres
CREATE DATABASE fidden_local;
\q
```

### Step 3: Import SQL Dump

```bash
# Import the SQL file into your local database
psql fidden_local < fidden.sql

# This will restore all tables, data, and relationships
```

### Step 4: Update .env for Local Database

Add to your `.env` file (or create `.env.local`):

```bash
# Local PostgreSQL Database
DATABASE_URL=postgresql://YOUR_USERNAME@localhost:5432/fidden_local

# OR if you have a password
DATABASE_URL=postgresql://YOUR_USERNAME:YOUR_PASSWORD@localhost:5432/fidden_local

# Example (replace 'fionabari' with your Mac username):
DATABASE_URL=postgresql://fionabari@localhost:5432/fidden_local
```

### Step 5: Test Connection

```bash
# Test database connection
.venv/bin/python manage.py check --database default

# Run migrations (to add Consultation table)
.venv/bin/python manage.py migrate

# Start server
.venv/bin/python manage.py runserver
```

---

## Quick Setup Script

Run this entire script:

```bash
# 1. Create database
createdb fidden_local

# 2. Import SQL dump
psql fidden_local < fidden.sql

# 3. Update .env (replace YOUR_USERNAME)
echo "DATABASE_URL=postgresql://$(whoami)@localhost:5432/fidden_local" >> .env.local

# 4. Run migrations
.venv/bin/python manage.py migrate

# 5. Start server
.venv/bin/python manage.py runserver
```

---

## Troubleshooting

**Error: "createdb: command not found"**
- PostgreSQL is not installed. Run: `brew install postgresql@15`

**Error: "psql: could not connect to server"**
- Start PostgreSQL: `brew services start postgresql@15`

**Error: "database already exists"**
- Drop and recreate: `dropdb fidden_local && createdb fidden_local`

**Error: "permission denied"**
- Add your user: `createuser -s $(whoami)`

---

## Verify Data Imported

```bash
# Connect to database
psql fidden_local

# Check tables
\dt

# Check shop count
SELECT COUNT(*) FROM api_shop;

# Check users
SELECT id, email, role FROM accounts_customuser LIMIT 5;

# Exit
\q
```

---

## Alternative: Use Docker PostgreSQL

If you prefer Docker:

```bash
# Run PostgreSQL in Docker
docker run --name fidden-postgres \
  -e POSTGRES_PASSWORD=fidden123 \
  -e POSTGRES_DB=fidden_local \
  -p 5432:5432 \
  -d postgres:15

# Import SQL
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql

# Update .env
DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local
```

---

## What You Get

After importing the SQL dump, you'll have:
- ✅ All production data locally
- ✅ All users and shops
- ✅ All services and bookings
- ✅ All reviews and ratings
- ✅ Complete test environment

You can then run migrations to add the new Consultation table!
