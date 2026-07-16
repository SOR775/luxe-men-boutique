"""LUXE MEN — Production Settings"""
from .base import *  # noqa
import os

DEBUG = False

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# PostgreSQL
DATABASES = {
    'default': env.db('DATABASE_URL')
}

# Redis Cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'ssl_cert_reqs': None,
            },
        }
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Channels with Redis (Upstash requires SSL + keepalive)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [{
                'address': env('REDIS_URL'),
                'ssl_cert_reqs': None,
            }],
            'capacity': 100,
            'expiry': 60,
        },
    }
}

# Static
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_MANIFEST_STRICT = False

# Email - Using Resend HTTP API instead of blocked SMTP
EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
ANYMAIL = {
    "RESEND_API_KEY": env('RESEND_API_KEY', default=''),
}

