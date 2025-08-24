# Use Python 3.11 slim
FROM python:3.11-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

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

# Expose port
EXPOSE 8090

# Default command to run Django
CMD ["gunicorn", "fidden.wsgi:application", "--bind", "0.0.0.0:8090"]
