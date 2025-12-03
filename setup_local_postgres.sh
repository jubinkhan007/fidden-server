#!/bin/bash
# Setup PostgreSQL Locally (Using Homebrew, not Docker)

echo "🚀 Setting up local PostgreSQL with fidden.sql data..."

# Step 1: Start PostgreSQL service
echo "1. Starting PostgreSQL service..."
brew services start postgresql@15
sleep 5

# Step 2: Create database
echo "2. Creating database 'fidden_local'..."
createdb fidden_local

# Step 3: Import SQL dump
echo "3. Importing fidden.sql (this will take 30-60 seconds)..."
psql fidden_local < fidden.sql

# Step 4: Verify import
echo "4. Verifying data import..."
psql fidden_local -c "SELECT COUNT(*) FROM api_shop;"

# Step 5: Update .env
echo "5. Updating .env file..."
USERNAME=$(whoami)
echo "DATABASE_URL=postgresql://$USERNAME@localhost:5432/fidden_local" >> .env

echo ""
echo "✅ Database setup complete!"
echo ""
echo "Database Info:"
echo "  - Database name: fidden_local"
echo "  - Connection: postgresql://$USERNAME@localhost:5432/fidden_local"
echo ""
echo "Next steps:"
echo "  1. Run migrations: .venv/bin/python manage.py migrate"
echo "  2. Start server: .venv/bin/python manage.py runserver"
