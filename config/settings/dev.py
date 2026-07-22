"""LUXE MEN — Development Settings"""
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Use Gmail SMTP for development email delivery
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Django Debug Toolbar
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
INTERNAL_IPS = ['127.0.0.1']

# Disable password hashing for speed in tests
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Media files served by Django dev server
# DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
