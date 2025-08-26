FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=fidden.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .

# Fail fast if project files missing
RUN test -f /app/manage.py && test -d /app/fidden || (echo "ERROR: Project files missing!" && exit 1)

EXPOSE 8090

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "fidden.wsgi:application", "--bind", "0.0.0.0:8090", "--workers=4", "--threads=2", "--timeout=120"]
