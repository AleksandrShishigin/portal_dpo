import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
if os.getenv('DPO_DEMO') != '1':
    load_dotenv(ROOT_DIR / '.env')
# Generate a persistent local secret outside tracked source; never log its value.
secret_dir = ROOT_DIR / '.local'
secret_dir.mkdir(exist_ok=True)
secret_file = secret_dir / 'django-secret'
if not os.getenv('DJANGO_SECRET_KEY') and not secret_file.exists():
    try:
        with secret_file.open('x', encoding='utf-8') as f:
            f.write(get_random_secret_key())
    except FileExistsError:
        pass
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY') or secret_file.read_text(encoding='utf-8')
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'rest_framework', 'portal']
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': os.getenv('DB_HOST', 'localhost'), 'PORT': os.getenv('DB_PORT', '5432'),
    'NAME': os.getenv('DB_NAME', 'dpo_portal'), 'USER': os.getenv('DB_USER', 'dpo_app'),
    'PASSWORD': os.getenv('DB_PASSWORD', ''),
}}
AUTH_USER_MODEL = 'portal.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '60/minute'},
}
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
MEDIA_ROOT = ROOT_DIR / 'private-media'
# No public MEDIA_URL route: attachments are served only by permission-checked API.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
CSRF_FAILURE_VIEW = 'portal.views.csrf_failure'

# No consent is invented on behalf of the university. Drafts remain available.
CONSENT_VERSION = os.getenv('CONSENT_VERSION', '')
_consent_file = os.getenv('CONSENT_TEXT_FILE', '')
_consent_path = Path(_consent_file) if Path(_consent_file).is_absolute() else ROOT_DIR / _consent_file
CONSENT_TEXT = (_consent_path.read_text(encoding='utf-8-sig') if _consent_file else os.getenv('CONSENT_TEXT', ''))
PROTOTYPE_MODE = os.getenv('DPO_PROTOTYPE', 'false').lower() == 'true'
if PROTOTYPE_MODE:
    from .prototype_consent import PROTOTYPE_CONSENT_TEXT, PROTOTYPE_CONSENT_VERSION
    CONSENT_TEXT = PROTOTYPE_CONSENT_TEXT
    CONSENT_VERSION = PROTOTYPE_CONSENT_VERSION

TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True}]
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.dummy.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'false').lower() == 'true'
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@localhost')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://127.0.0.1:5173').rstrip('/')
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', '3600'))
