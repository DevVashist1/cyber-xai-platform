import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory: module2/backend/
BASE_DIR = Path(__file__).resolve().parent.parent

# Root project directory: cyber-xai-platform-main/ (where .env lives)
ROOT_DIR = BASE_DIR.parent.parent
load_dotenv(ROOT_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-fallback-secret-key')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party libraries
    'rest_framework',
    'corsheaders',
    # Module 2 Apps
    'apps.devices',
    'apps.events',
    'apps.distribution',
    'apps.feedback',
    'apps.behavior',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Connect to your Module 1 Postgres container
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', os.getenv('DB_NAME', 'insider_threat_db')),
        'USER': os.getenv('POSTGRES_USER', os.getenv('DB_USER', 'postgres')),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', os.getenv('DB_PASSWORD', 'postgres')),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Allow the Chrome Extension to send data to localhost
CORS_ALLOW_ALL_ORIGINS = True

# Redis and Enrollment settings
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
ENROLLMENT_CODE = os.getenv('ENROLLMENT_CODE', 'team-secret-code-2026')