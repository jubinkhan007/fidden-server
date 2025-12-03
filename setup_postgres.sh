#!/bin/bash
# Docker PostgreSQL Setup Script
# Run this in your terminal

echo "🚀 Setting up PostgreSQL in Docker..."

# Stop any existing container
echo "1. Removing old container if exists..."
docker rm -f fidden-postgres 2>/dev/null || true

# Create PostgreSQL container
echo "2. Creating PostgreSQL container..."
docker run --name fidden-postgres \
  -e POSTGRES_PASSWORD=fidden123 \
  -e POSTGRES_DB=fidden_local \
  -p 5432:5432 \
  -d postgres:15

# Wait for PostgreSQL to initialize
echo "3. Waiting for PostgreSQL to start (10 seconds)..."
sleep 10

# Import SQL dump
echo "4. Importing SQL dump (this may take 30-60 seconds)..."
docker exec -i fidden-postgres psql -U postgres fidden_local < fidden.sql

# Check if import was successful
echo "5. Verifying import..."
docker exec -it fidden-postgres psql -U postgres fidden_local -c "\dt" | head -20

# Update .env
echo "6. Updating .env file..."
echo 'DATABASE_URL=postgresql://postgres:fidden123@localhost:5432/fidden_local' >> .env

echo "✅ Database setup complete!"
echo ""
echo "Next steps:"
echo "1. Run migrations: .venv/bin/python manage.py migrate"
echo "2. Start server: .venv/bin/python manage.py runserver"
