"""用固定版本 ClamAV 容器验收 clean 与 EICAR 拒收路径。"""
import argparse
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))

EICAR = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_ENV', 'testing')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.testing')
    os.environ['ADMINCORE_ANTIVIRUS_ENABLED'] = 'True'
    os.environ['ADMINCORE_CLAMAV_ADDRESS'] = '127.0.0.1'
    os.environ['ADMINCORE_CLAMAV_PORT'] = str(args.port)
    import django
    django.setup()
    from apps.files.antivirus import ScanRejected, checked_copy, scan_context

    context = {'results': [], 'artifacts': []}
    token = scan_context.set(context)
    try:
        with checked_copy(io.BytesIO(b'admincore-clean'), stage='real_engine') as clean:
            assert clean.read() == b'admincore-clean'
        try:
            checked_copy(io.BytesIO(EICAR), stage='real_engine')
        except ScanRejected as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError('EICAR was not rejected')
    finally:
        scan_context.reset(token)
    assert [result['outcome'] for result, _ in context['results']] == ['clean', 'infected']
    print('ClamAV 1.5.4 real-engine validation passed: clean + EICAR rejected')


if __name__ == '__main__':
    main()
