"""Loopback-only demonstration, using the isolated demo PostgreSQL and files."""
from .demo_settings import *  # noqa: F403

ALLOWED_HOSTS = ['127.0.0.1']
FRONTEND_URL = 'http://127.0.0.1:5174'
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]
# Local HTTP only. The externally published HTTPS demo keeps Secure cookies.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_NAME = 'dpo_local_demo_session'
CSRF_COOKIE_NAME = 'dpo_local_demo_csrf'
