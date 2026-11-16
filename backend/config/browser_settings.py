"""Separate local browser QA database and uploads; never the project DB."""
from .test_settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':ROOT_DIR/'.local/browser-qa.sqlite3'}}
MEDIA_ROOT = ROOT_DIR/'.local/browser-qa-media'
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:5175']
FRONTEND_URL = 'http://127.0.0.1:5175'
from .demo_consent import DEMO_CONSENT_TEXT, DEMO_CONSENT_VERSION
CONSENT_TEXT = DEMO_CONSENT_TEXT
CONSENT_VERSION = DEMO_CONSENT_VERSION
DEMO_CONFIRMATION = True
SESSION_COOKIE_NAME = 'dpo_browser_qa_session'
CSRF_COOKIE_NAME = 'dpo_browser_qa_csrf'
if os.environ.get('DPO_QA_CONSENT_UNAVAILABLE') == '1':
    CONSENT_TEXT = ''
    CONSENT_VERSION = ''
