"""
LUXE MEN — Django Base Settings
"""
import os
import sys
from pathlib import Path
from celery.schedules import crontab
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
)

environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
if DEBUG:
    ALLOWED_HOSTS.extend(['.ngrok-free.app', '.ngrok-free.dev', 'localhost', '127.0.0.1'])
    CSRF_TRUSTED_ORIGINS = [
        'https://*.ngrok-free.app', 'http://*.ngrok-free.app',
        'https://*.ngrok-free.dev', 'http://*.ngrok-free.dev',
        'http://localhost:8000', 'http://127.0.0.1:8000'
    ]

# ─── Site Info ────────────────────────────────────────────────────────────────
SITE_NAME = env('SITE_NAME', default='LUXE MEN')
SITE_URL = env('SITE_URL', default='http://localhost:8000')
CURRENCY_CODE = env('CURRENCY_CODE', default='KES')
CURRENCY_SYMBOL = env('CURRENCY_SYMBOL', default='KSh')

# ─── Applications ─────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'django_filters',
    'channels',
    'anymail',
]

LOCAL_APPS = [
    'core',
    'accounts',
    'products',
    'inventory',
    'orders',
    'payments',
    'escrow',
    'shipping',
    'marketing',
    'analytics',
    'notifications',
    'support',
    'wallets',
    'api',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

SITE_ID = 1

# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.SecurityHeadersMiddleware',
    'core.middleware.ActivityLogMiddleware',
    'core.middleware.StaffSessionTimeoutMiddleware',
]

# Staff sessions get a much shorter sliding idle timeout than regular
# customer sessions (which use SESSION_COOKIE_AGE below). 15 minutes by
# default — override via env if that's too aggressive for your admins.
STAFF_SESSION_TIMEOUT_SECONDS = env.int('STAFF_SESSION_TIMEOUT_SECONDS', default=900)

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ─── Templates ────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_settings',
                'core.context_processors.cart_count',
                'core.context_processors.notifications_count',
                'core.context_processors.admin_permissions',
                'core.context_processors.returning_customer_banner',
            ],
        },
    },
]

# ─── Database ────────────────────────────────────────────────────────────────
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3')
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Auth ────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# Account lockout settings
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30
EMAIL_LOGIN_CODE_EXPIRY_MINUTES = 10

# ─── Internationalization ────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# ─── Static & Media ─────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
if 'test' in sys.argv or 'pytest' in sys.modules:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = env('MEDIA_URL', default='/media/')
MEDIA_ROOT = BASE_DIR / env('MEDIA_ROOT', default='media')

# ─── Email ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='LUXE MEN <noreply@luxemen.com>')

# ─── Cache & Redis ────────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# ─── Session ─────────────────────────────────────────────────────────────────
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_COOKIE_HTTPONLY = True

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 24,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

# ─── JWT ─────────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─── DRF Spectacular (Swagger) ────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'LUXE MEN API',
    'DESCRIPTION': 'Premium Men\'s Boutique E-Commerce REST API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]
CORS_ALLOW_CREDENTIALS = True

# ─── M-Pesa ──────────────────────────────────────────────────────────────────
MPESA_ENVIRONMENT = env('MPESA_ENVIRONMENT', default='sandbox')
MPESA_CONSUMER_KEY = env('MPESA_CONSUMER_KEY', default='')
MPESA_CONSUMER_SECRET = env('MPESA_CONSUMER_SECRET', default='')
MPESA_SHORTCODE = env('MPESA_SHORTCODE', default=env('MPESA_BUSINESS_SHORTCODE', default='174379'))
MPESA_PASSKEY = env('MPESA_PASSKEY', default='')
MPESA_CALLBACK_URL = env('MPESA_CALLBACK_URL', default='http://localhost:8000/payments/mpesa/callback/')

# ─── Celery ──────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# SSL options required for Upstash rediss:// TLS connections
import ssl as _ssl
CELERY_BROKER_USE_SSL = {
    'ssl_cert_reqs': _ssl.CERT_NONE
}
CELERY_REDIS_BACKEND_USE_SSL = {
    'ssl_cert_reqs': _ssl.CERT_NONE
}
CELERY_BEAT_SCHEDULE = {
    'escrow-auto-release': {
        'task': 'escrow.tasks.auto_release_expired_escrows',
        'schedule': crontab(minute=0, hour='*/1'),
        'options': {'expires': 3600},
    },
}

# ─── Channels ────────────────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# ─── Security Headers ────────────────────────────────────────────────────────
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# ─── Logging ─────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'accounts': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'payments': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}
