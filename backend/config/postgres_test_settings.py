"""Only the isolated cluster started by scripts/test-postgres.py is accepted."""
from .test_settings import *  # noqa: F403
import os

if os.getenv('DPO_ISOLATED_PG_TESTS') != '1':
    raise RuntimeError('Run scripts/test-postgres.py; do not use this with the project database.')
DATABASES = {'default': {
    'ENGINE':'django.db.backends.postgresql','NAME':'dpo_tests','USER':'dpo_test_runner',
    'HOST':'127.0.0.1','PORT':'55439','PASSWORD':'',
    'TEST':{'NAME':'test_dpo_tests'},
}}
