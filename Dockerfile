# Use python:3.11-slim
FROM python:3.11-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/app
ENV DJANGO_SETTINGS_MODULE=fidden.settings

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Fail fast if project files are missing from the build context
RUN ls -la /app && \
    test -f /app/manage.py && \
    test -d /app/fidden || (echo "ERROR: Project files missing in image. Ensure Coolify build context is the repo root containing manage.py and fidden/." && exit 1)

# Expose port
EXPOSE 8090

# Add entrypoint that validates imports then launches the app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "fidden.wsgi:application", "--bind", "0.0.0.0:8090"]
