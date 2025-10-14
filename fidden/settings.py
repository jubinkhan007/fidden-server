#fidden/settings.py

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import json


# Load .env file
load_dotenv()
# ==============================
# Base Directory
# ==============================
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================
# Media
# ==============================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==============================
# Django Security
# ==============================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')
SAFE_REDIRECT_SCHEMES = ["http", "https", "myapp"]

# ==============================
# Installed Apps
# ==============================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'accounts',
    'api',
    'payments',
    'subscriptions',
    'django_celery_beat',
    'channels',
    'drf_yasg',
    # 'django_crontab',
]

# CRONJOBS = [
#     ('0 0 * * *', 'api.cron.generate_slots_cron')  # daily at midnight
# ]

# ==============================
# REST Framework & JWT
# ==============================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ==============================
# Middleware
# ==============================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static file compression
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fidden.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'fidden.wsgi.application'

# Channels / Redis with env-based config and safe fallback (best for free Render)
ASGI_APPLICATION = "fidden.asgi.application"

REDIS_URL = os.getenv("REDIS_URL")
CHANNEL_LAYER_BACKEND = os.getenv("CHANNEL_LAYER_BACKEND", "memory").lower()

if CHANNEL_LAYER_BACKEND == "redis" and REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ==============================
# Database
# ==============================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_NAME', 'fidden'),
        'USER': os.getenv('DATABASE_USER', 'postgres'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', ''),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': int(os.getenv('DATABASE_PORT', 5432)),
    }
}

# ==============================
# Password Validation
# ==============================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

LOGGING = {
  "version": 1,
  "disable_existing_loggers": False,
  "handlers": {
    "console": {"class": "logging.StreamHandler"},
  },
  "loggers": {
    "": {"handlers": ["console"], "level": "INFO"},
  },
}

# ==============================
# Internationalization
# ==============================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# ==============================
# Static files
# ==============================
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ==============================
# Default primary key field type
# ==============================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================
# Media Files
# ==============================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==============================
# Email Configuration
# ==============================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Fidden <no-reply@fidden.com>')

# ==============================
# Custom User Model
# ==============================
AUTH_USER_MODEL = 'accounts.User'

# ==============================
# Google OAuth Client IDs
# ==============================
GOOGLE_CLIENT_IDS = {}
google_ids_str = os.getenv('GOOGLE_CLIENT_IDS', '')
if google_ids_str:
    for pair in google_ids_str.split(','):
        key, value = pair.split('=')
        GOOGLE_CLIENT_IDS[key.strip()] = value.strip()

# ==============================
# CSRF Trusted Origins
# ==============================
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if x]

# ==============================
# Celery Configuration
# ==============================
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = os.getenv('CELERY_TIMEZONE', TIME_ZONE)
CELERY_ENABLE_UTC = True


FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")
FCM_SERVICE_ACCOUNT_FILE = os.environ.get("FCM_SERVICE_ACCOUNT_JSON", "{}")
#laod FCM from config env variable
try:
    FCM_SERVICE_ACCOUNT_JSON = json.loads(FCM_SERVICE_ACCOUNT_FILE)
    print("Fcm config loaded from env")
except json.JSONDecodeError:
    FCM_SERVICE_ACCOUNT_JSON= {}
    print("Missing the json file")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")  # sk_test_...
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")  # pk_test_...
STRIPE_ENDPOINT_SECRET = os.environ.get("STRIPE_ENDPOINT_SECRET")  # webhook secret


STRIPE_SUCCESS_URL = os.getenv('STRIPE_SUCCESS_URL', 'http://localhost:3000/subscription/success')
STRIPE_CANCEL_URL = os.getenv('STRIPE_CANCEL_URL', 'http://localhost:3000/subscription/cancel')