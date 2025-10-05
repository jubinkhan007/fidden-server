## Fidden Backend (Django + DRF + Channels)

Production-ready backend for Fidden built with Django 5, Django REST Framework, Channels (WebSockets), Celery, Redis, and Stripe. Ships with Docker and Uvicorn, static handling via WhiteNoise, health checks, and background jobs.

### Features
- **API**: Django REST Framework with JWT auth
- **Real-time**: Django Channels (Redis/In-memory)
- **Async jobs**: Celery + Redis, optional Beat scheduler with `django-celery-beat`
- **Payments**: Stripe intents, onboarding, card saving, and webhook
- **Notifications**: FCM support
- **OAuth**: Google sign-in client ID mapping
- **Static/Media**: WhiteNoise + `/media` mounted
- **Health**: `GET /health/` endpoint

### Installation Guide
1) Clone the repository and move into `backend/`.
2) Create `.env` from the template and configure values (see Environment Variables below).
3) Choose one of the following:
- Docker (recommended): follow "Docker build and run".
- Local install: follow "Local Development (without Docker)".

### Docker build and run
Build and start all services in the background:
```bash
# Newer Docker versions
docker compose up -d --build

# Legacy syntax (as in note.txt)
docker-compose up -d --build
```

Run database migrations:
```bash
docker compose exec web python manage.py migrate
# or
docker-compose exec web python manage.py migrate
```

Create a superuser:
```bash
docker compose exec web python manage.py createsuperuser
# or
docker-compose exec web python manage.py createsuperuser
```

Make new migrations (when you change models):
```bash
docker compose exec web python manage.py makemigrations
# or
docker-compose exec web python manage.py makemigrations
```

Watch logs:
```bash
docker compose logs -f web
# or
docker-compose logs -f web
```

Stop services:
```bash
docker compose down
# or
docker-compose down
```

### Requirements
- Docker and Docker Compose (recommended) OR
- Python 3.13, PostgreSQL 14+, Redis 6+

### Quickstart (Docker)
1) Copy the example env and adjust values:
```bash
cp .env.example .env
```
2) Build and start services:
```bash
docker compose up --build -d
```
3) Apply migrations and create a superuser (first run):
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```
4) Open:
- API/Docs: http://localhost:8090/
- Admin: http://localhost:8090/admin/
- Health: http://localhost:8090/health/

### Local Development (without Docker)
1) Create and activate a virtualenv with Python 3.13, then:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
2) Ensure PostgreSQL and Redis are running. Export env vars from `.env`.
3) Migrate and run:
```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8090
```
4) Channels (websockets) with Redis in dev: set `CHANNEL_LAYER_BACKEND=redis` and `REDIS_URL=redis://localhost:6379/0`.

### Services and Ports
- Web/API: `8090` (mapped to container `8090`)
- Redis: host `6385` → container `6379` (see `docker-compose.yml`)

### Running Background Workers
Docker Compose brings up:
- `web`: Uvicorn serving `fidden.asgi:application`
- `celery`: Celery worker (`celery -A fidden worker`)
- `celery-beat`: Celery Beat with `django_celery_beat` scheduler
- `redis`: Redis 8

Manually (no Docker):
```bash
celery -A fidden worker --loglevel=info
celery -A fidden beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Static and Media Files
- Collected into `/app/staticfiles` using WhiteNoise (`collectstatic` runs in Docker build and entrypoint)
- User uploads served from `/media` volume

Local dev tips:
```bash
python manage.py collectstatic --noinput
```

### Health Check
- `GET /health/` returns `{ "status": "ok" }`

### Payments (Stripe)
- API routes under `payments/`:
  - `POST /payments/payment-intent/<booking_id>/`
  - `GET /payments/shop-onboarding/<shop_id>/`
  - `POST /payments/save-card/`
  - `GET /payments/shops/verify-onboarding/<shop_id>`
- Webhook: `POST /stripe-webhook/`
  - Configure in Stripe Dashboard using your public URL (e.g. `https://your.domain/stripe-webhook/`)
  - Use `STRIPE_ENDPOINT_SECRET` to verify signatures

### Authentication
- JWT via `djangorestframework_simplejwt`
- `Authorization: Bearer <token>`

### Channels / WebSockets
- ASGI app: `fidden.asgi:application`
- Default: In-memory layer; set `CHANNEL_LAYER_BACKEND=redis` and `REDIS_URL` for production

### Database
- Default engine is PostgreSQL. Configure via env vars in `.env`.
- Apply migrations on deploy:
```bash
python manage.py migrate --noinput
```

### Admin
Create an admin user:
```bash
python manage.py createsuperuser
```

### Production Deployment Notes
- Set `DEBUG=False`, configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Use a reverse proxy (e.g., Nginx) terminating TLS → upstream `web:8090`
- Ensure `collectstatic` runs and static files are served by WhiteNoise (already enabled)
- Use a managed PostgreSQL and Redis service
- Run separate processes for `web`, `celery`, and `celery-beat`
- Configure log aggregation and monitoring; Docker healthchecks are provided

Example Nginx upstream snippet:
```nginx
location / {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://web:8090;
}
```

### Development Tips
- Use `docker compose logs -f web celery celery-beat` for troubleshooting
- Access a shell in the container: `docker compose exec web bash`
- Run tests: `python manage.py test`

### Project Structure (selected)
```
backend/
  accounts/            # Custom user & auth
  api/                 # Core API endpoints
  payments/            # Stripe endpoints + webhook
  fidden/              # Django project (settings, asgi, urls)
  Dockerfile
  docker-compose.yml
  entrypoint.sh
  requirements.txt
```

### Security Checklist
- Rotate `SECRET_KEY` and third-party credentials regularly
- Enforce HTTPS at the proxy; set HSTS
- Keep `ALLOWED_HOSTS` tight; avoid `*` in production
- Validate CORS/CSRF according to your frontend origins
- Regularly update `requirements.txt` and rebuild images

---

If you run into setup issues, please share the exact command and full error output.


