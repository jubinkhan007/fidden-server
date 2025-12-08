#fidden/settings.py

import os
from pathlib import Path
from datetime import timedelta
import ssl
from dotenv import load_dotenv
import json
import urllib.parse as urlparse


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
    'payments',
    'subscriptions',
    'django_celery_beat',
    'channels',
    'drf_yasg',
    'api.apps.ApiConfig',
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
# ==============================
# Helper logic to clean Redis URL
# ==============================

# Get the raw URL from the environment
RAW_REDIS_URL = os.getenv("REDIS_URL")
CLEAN_REDIS_URL = RAW_REDIS_URL
SSL_OPTIONS = {}

if RAW_REDIS_URL and RAW_REDIS_URL.startswith("rediss://"):
    # This is an SSL connection, set the correct SSL constant
    SSL_OPTIONS = {"ssl_cert_reqs": ssl.CERT_NONE}
    
    try:
        # Parse the URL
        parsed_url = urlparse.urlparse(RAW_REDIS_URL)
        
        # Parse query parameters
        query_params = urlparse.parse_qs(parsed_url.query)
        
        # Remove the problematic key if it exists
        query_params.pop('ssl_cert_reqs', None)
        
        # Rebuild the query string
        new_query = urlparse.urlencode(query_params, doseq=True)
        
        # Reconstruct the URL without the problematic param
        CLEAN_REDIS_URL = parsed_url._replace(query=new_query).geturl()
        
    except Exception as e:
        # Fallback in case of parsing error
        print(f"Warning: Could not parse REDIS_URL, proceeding with raw URL. Error: {e}")
        CLEAN_REDIS_URL = RAW_REDIS_URL

# ==============================
# Channels / Redis
# ==============================
ASGI_APPLICATION = "fidden.asgi.application"

CHANNEL_LAYER_BACKEND = os.getenv("CHANNEL_LAYER_BACKEND", "memory").lower()

if CHANNEL_LAYER_BACKEND == "redis" and RAW_REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # Use the CLEANED URL here
                "hosts": [CLEAN_REDIS_URL],
                # Pass the SSL options generated above
                **SSL_OPTIONS, 
            },
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
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s:%(lineno)s — %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Root logger
        "": {"handlers": ["console"], "level": "INFO"},

        # Django core
        "django": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "DEBUG", "propagate": False},

        # Email backend
        "django.core.mail": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
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
USE_S3 = os.getenv("USE_S3", "true").lower() == "true"

if USE_S3:
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")

    AWS_ACCESS_KEY_ID       = os.getenv("S3_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY   = os.getenv("S3_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    AWS_S3_REGION_NAME      = os.getenv("S3_REGION")  # e.g. ap-south-1

    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_ADDRESSING_STYLE  = "virtual"
    AWS_DEFAULT_ACL          = None
    AWS_QUERYSTRING_AUTH     = False
    AWS_S3_FILE_OVERWRITE    = False

    STORAGES = {
    "default": {"BACKEND": "fidden.storage_backends.MediaStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

    # If you have CloudFront/custom domain, set S3_PUBLIC_DOMAIN in env.
    S3_PUBLIC_DOMAIN = os.getenv("S3_PUBLIC_DOMAIN")
    if S3_PUBLIC_DOMAIN:
        MEDIA_URL = f"https://{S3_PUBLIC_DOMAIN}/"
    else:
        # Standard AWS S3 public URL with region
        AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
else:
    MEDIA_URL  = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# ==============================
# Email Configuration in settings.py
# ==============================

#'django.core.mail.backends.console.EmailBackend' if DEBUG else 

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() in ('true','1','yes')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'false').lower() in ('true','1','yes')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', 20))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Fidden <no-reply@fidden.test>')

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
# Add localhost for local development
CSRF_TRUSTED_ORIGINS += ['http://localhost:8000', 'http://127.0.0.1:8000']

# ==============================
# Celery Configuration
# ==============================


# Use the Redis URL you defined earlier in this file
CELERY_BROKER_URL = CLEAN_REDIS_URL
CELERY_RESULT_BACKEND = CLEAN_REDIS_URL
CELERY_TASK_IGNORE_RESULT = True

# Sync Celery's timezone with Django's
CELERY_TIMEZONE = TIME_ZONE

# By removing or commenting out CELERY_TASK_ALWAYS_EAGER, 
# tasks will now be sent to the worker.
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_TASK_EAGER_PROPAGATES = True



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
STRIPE_AI_PRICE_ID = os.environ.get("STRIPE_AI_PRICE_ID")

STRIPE_SUCCESS_URL = os.getenv('STRIPE_SUCCESS_URL', 'http://localhost:3000/subscription/success')
STRIPE_CANCEL_URL = os.getenv('STRIPE_CANCEL_URL', 'http://localhost:3000/subscription/cancel')
STRIPE_LEGACY_COUPON_ID = os.environ.get("STRIPE_LEGACY_COUPON_ID")
STRIPE_LEGACY_PROMO_CODE_ID = os.environ.get("STRIPE_LEGACY_PROMO_CODE_ID")


# PayPal Configuration
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_SECRET = os.getenv('PAYPAL_SECRET')
PAYPAL_BASE_URL = os.getenv('PAYPAL_BASE_URL', 'https://api-m.sandbox.paypal.com')
PAYPAL_AI_ADDON_AMOUNT = "39.99"  # Or whatever price you want
PAYPAL_CURRENCY_CODE = "USD"
PAYPAL_PLAN_MOMENTUM_ID = os.getenv("PAYPAL_PLAN_MOMENTUM_ID", default="")
PAYPAL_PLAN_ICON_ID = os.getenv("PAYPAL_PLAN_ICON_ID", default="")
PAYPAL_PLAN_AI_ADDON_ID = os.getenv("PAYPAL_PLAN_AI_ADDON_ID", default="")


# pip install django-redis
# CACHES (Redis if REDIS_URL provided, else LocMem)
if CLEAN_REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": CLEAN_REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                # Avoid 500s if Redis hiccups; cache calls just return None.
                "IGNORE_EXCEPTIONS": True,
                # Pass SSL options if using rediss://
                "CONNECTION_POOL_KWARGS": {**SSL_OPTIONS},
            },
            "TIMEOUT": 60,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "fidden-default",
        }
    }

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")  # fallback if no messaging service
TWILIO_ENABLE = os.getenv("TWILIO_ENABLE", True)

ZAPIER_KLAVIYO_WEBHOOK = os.getenv("ZAPIER_KLAVIYO_WEBHOOK", "")