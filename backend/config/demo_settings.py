"""Isolated demonstration settings. Never load the working project's .env."""
import json
import os
from pathlib import Path

if os.environ.get('DPO_DEMO') != '1':
    raise RuntimeError('Use scripts/demo.py to select the isolated environment.')

from .settings import *

_demo = ROOT_DIR / '.local' / 'demo'
_config = json.loads((_demo / 'config.json').read_text(encoding='utf-8'))
DEBUG = False
SECRET_KEY = _config['secret_key']
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
    'HOST': '127.0.0.1', 'PORT': '55440', 'NAME': 'dpo_demo',
    'USER': 'dpo_demo_app', 'PASSWORD': _config['app_password']}}
MEDIA_ROOT = _demo / 'documents'
_host = os.environ.get('DPO_DEMO_HOST', 'demo-preflight.invalid')
from .demo_hosts import valid_demo_host
if not (_host == 'demo-preflight.invalid' or valid_demo_host(_host)):
    raise RuntimeError('Invalid exact demo hostname')
ALLOWED_HOSTS = [_host]
CSRF_TRUSTED_ORIGINS = ['https://' + _host]
FRONTEND_URL = 'https://' + _host
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = 'dpo_demo_session'
CSRF_COOKIE_NAME = 'dpo_demo_csrf'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 3600
MIDDLEWARE = [*MIDDLEWARE, 'django.middleware.clickjacking.XFrameOptionsMiddleware']
SECURE_SSL_REDIRECT = True
# Waitress sets the scheme; client-supplied proxy headers are not trusted.
from .demo_consent import DEMO_CONSENT_TEXT, DEMO_CONSENT_VERSION
CONSENT_TEXT = DEMO_CONSENT_TEXT
CONSENT_VERSION = DEMO_CONSENT_VERSION
DEMO_CONFIRMATION = True
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
EMAIL_HOST_PASSWORD = ''
