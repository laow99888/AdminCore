"""Run only isolated OIDC/RSA and TLS fixtures; never connects to deployment services or reads credentials."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    executable = root / 'backend' / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.is_file():
        executable = Path(sys.executable)
    environment = os.environ.copy()
    environment['DJANGO_SETTINGS_MODULE'] = 'config.settings.testing'
    # testing settings override the DB/cache/storage. Protocol fixture enables loopback only inside TESTING.
    result = subprocess.run([str(executable), '-X', 'utf8', '-m', 'pytest',
                             'tests/test_sso.py', 'tests/test_sso_transport.py',
                             '-o', 'addopts=', '-q'], cwd=root / 'backend', env=environment, check=False)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
