from .settings import *  # noqa: F403
import tempfile

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
_test_media = tempfile.TemporaryDirectory(prefix='dpo-tests-')
MEDIA_ROOT = _test_media.name
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CONSENT_VERSION = 'automated-test-v1'
CONSENT_TEXT = 'Текст исключительно для автоматических тестов.'
PROTOTYPE_MODE = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
