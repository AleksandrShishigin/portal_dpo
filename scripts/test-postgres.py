"""Start an independent, loopback-only PostgreSQL cluster for tests, then stop it.

No production credentials, services, authentication files or databases are used.
The disposable cluster remains under ignored .local/ for repeat runs.
"""
from pathlib import Path
import os
import socket
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
BIN=Path(r'C:\Program Files\PostgreSQL\18\bin')
DATA=(ROOT/'.local/pg-tests').resolve()
PORT='55439'


def main():
    if not DATA.is_relative_to(ROOT/'.local'):
        sys.exit('Invalid test data path.')
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1',int(PORT)))
        except OSError:
            sys.exit('Test port 55439 is occupied; no existing process will be stopped.')
    env=os.environ.copy()
    env.pop('PGPASSWORD',None)
    env['DPO_ISOLATED_PG_TESTS']='1'
    env['PYTHONIOENCODING']='utf-8'
    def run(binary,*args,**kwargs):
        return subprocess.run([str(BIN/binary),*args],env=env,check=True,**kwargs)
    if not (DATA/'PG_VERSION').exists():
        DATA.parent.mkdir(exist_ok=True)
        run('initdb.exe','-D',str(DATA),'-U','dpo_test_runner','--auth=trust','--encoding=UTF8','--locale=C',stdout=subprocess.DEVNULL)
    started=False
    try:
        run('pg_ctl.exe','-D',str(DATA),'-l',str(ROOT/'.local/pg-tests-server.log'),'-o',f'-h 127.0.0.1 -p {PORT}','-w','start',stdout=subprocess.DEVNULL)
        started=True
        run('psql.exe','-X','-w','-h','127.0.0.1','-p',PORT,'-U','dpo_test_runner','-d','postgres','-v','ON_ERROR_STOP=1',
            input="SELECT 'CREATE DATABASE dpo_tests' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='dpo_tests')\n\\gexec\n",text=True,stdout=subprocess.DEVNULL)
        return subprocess.run([sys.executable,str(ROOT/'backend/manage.py'),'test','portal.tests','portal.test_workflows.ExtendedWorkflowTests',
            'portal.test_concurrency','portal.test_migrations','portal.test_profile_documents','portal.test_generated_documents',
            'portal.test_contract_signatures','--settings=config.postgres_test_settings','--noinput'],cwd=ROOT,env=env).returncode
    finally:
        if started:
            run('pg_ctl.exe','-D',str(DATA),'-m','fast','-w','stop',stdout=subprocess.DEVNULL)


if __name__=='__main__':
    sys.exit(main())
