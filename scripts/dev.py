"""Run the local Django and Vite processes, stopping both with Ctrl+C."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    node = shutil.which('node')
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.exists():
        sys.exit('Install frontend dependencies first: cd frontend; npm.cmd ci')
    if not (ROOT / '.env').exists():
        sys.exit('Missing .env. Copy .env.example to .env and configure PostgreSQL; see README.md.')
    # Avoid starting half a stack when a port is already in use.
    for port in (8000, 5173):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                sys.exit(f'Port {port} is busy. Stop the previous server first.')
    processes = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    try:
        processes.append(subprocess.Popen([sys.executable, str(ROOT / 'backend/manage.py'), 'runserver', '127.0.0.1:8000'], cwd=ROOT, creationflags=flags))
        processes.append(subprocess.Popen([node, str(vite), '--host', '127.0.0.1'], cwd=ROOT / 'frontend', creationflags=flags))
        print('Portal: http://127.0.0.1:5173 | API: http://127.0.0.1:8000/api/session/', flush=True)
        print('Ctrl+C stops both servers. Django and Vite reload source changes.', flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == 'nt':
                    try:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    except OSError:
                        process.terminate()
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    sys.exit(main())
