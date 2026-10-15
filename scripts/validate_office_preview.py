"""真实 Office 验收：新建随机项目/PG/环境；成功只清理本项目，失败停服务保留证据。"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid

import requests
from pypdf import PdfReader

from create_project import ROOT, create_project, compose_command, run_project, verify_ownership
from office_preview_fixtures import odf_fixture
import office_preview_runner as runner


# Trusted fixture generation only. Product converter and backend do not accept this interface.
EXPORT = '''import pathlib, subprocess, sys
src, dst = sys.argv[1:]
out = pathlib.Path('/tmp/output'); out.mkdir()
subprocess.run(['/usr/bin/soffice', '-env:UserInstallation=file:///tmp/profile', '--headless',
 '--nologo', '--nodefault', '--norestore', '--nofirststartwizard', '--convert-to', dst,
 '--outdir', str(out), '/input/source.' + src], check=True, timeout=60,
 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
target = out / ('source.' + dst)
assert target.is_file() and not target.is_symlink() and 0 < target.stat().st_size <= 10485760
sys.stdout.buffer.write(target.read_bytes())
'''


def export_fixture(source, image, extension, containers):
    """Generate real OOXML from trusted ODF using this reviewed LibreOffice image."""
    name = 'admincore-office-' + uuid.uuid4().hex
    containers.add(name)
    try:
        with runner.staged_source(name, source, image) as args:
            args[-2:] = ['-c', EXPORT, source.suffix[1:], extension]
            try:
                subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                result = subprocess.run(['docker', 'start', '--attach', name], check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=75)
            finally:
                subprocess.run(['docker', 'rm', '--force', name], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if not result.stdout.startswith(b'PK') or not 0 < len(result.stdout) <= runner.MAX_BYTES:
            raise ValueError('invalid_generated_fixture')
        return result.stdout
    finally:
        containers.remove(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='main 审查并准备的 image@sha256 仓库摘要')
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--frontend-port', type=int, default=18620)
    parser.add_argument('--backend-port', type=int, default=18621)
    options = parser.parse_args()
    if not runner.IMAGE.fullmatch(options.image):
        parser.error('必须传入受审查的固定仓库摘要，不能使用 latest/image ID')
    identifier = uuid.uuid4().hex
    evidence = ROOT / '.codex-validation' / ('admincore-office-' + identifier[:12])
    evidence.mkdir(parents=True, exist_ok=False)
    temporary = Path(tempfile.mkdtemp(prefix='admincore-office-validation-' + identifier + '-')).resolve()
    target = temporary / 'project'
    database = 'admincore_office_' + identifier
    report = {'passed': False, 'image': options.image, 'database': database, 'checks': []}
    containers = set()
    created = False
    new_password = secrets.token_urlsafe(40)
    member_password = secrets.token_urlsafe(40)
    member_name = 'office_' + identifier[:12]
    base_url = 'http://127.0.0.1:' + str(options.frontend_port) + '/api/v1/'
    all_jobs, source_ids = [], []

    def check(label, condition=True):
        if not condition:
            raise AssertionError(label)
        report['checks'].append(label)
        print('通过：' + label, flush=True)

    def command(args, *, payload=None, expected=0, timeout=180):
        verify_ownership(target)
        result = subprocess.run(compose_command(target, 'status')[:-1] + args, cwd=target,
            input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        # No stdout/stderr logging: claim output carries a one-time token and source bytes.
        check('隔离命令执行成功' if expected == 0 else '非法领取或完成立即拒绝',
              result.returncode == 0 if expected == 0 else result.returncode != 0)
        return result.stdout

    def shell(code):
        guard = ('from django.conf import settings\nfrom django.db import connection\n'
            'import os, json\nassert connection.vendor == "postgresql"\n'
            'assert settings.DATABASES["default"]["NAME"] == ' + repr(database) + '\n'
            'assert os.environ["COMPOSE_PROJECT_NAME"] == ' + repr(report['project']) + '\n')
        output = command(['exec', '-T', 'backend', 'python', 'manage.py', 'shell', '--no-imports',
            '-c', 'import sys;exec(sys.stdin.read())'], payload=(guard + code).encode())
        rows = [line.removeprefix('OFFICE_VALIDATION_JSON=') for line in output.decode().splitlines()
                if line.startswith('OFFICE_VALIDATION_JSON=')]
        return json.loads(rows[-1]) if rows else None

    def queue(action, data=None, *, expected=0):
        output = command(['exec', '-T', 'backend', 'python', 'manage.py', 'office_queue', action],
            payload=json.dumps(data).encode() if data else None, expected=expected)
        return json.loads(output) if expected == 0 else None

    def http(path, *, token=None, data=None, method='GET', expected=200, files=None, key=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        if key:
            headers['Idempotency-Key'] = key
        response = requests.request(method, base_url + path, headers=headers,
            json=data, files=files, timeout=35)
        check(path + ' HTTP ' + str(expected), response.status_code == expected)
        return response

    def login(username, password):
        return http('auth/login/', method='POST', data={'username': username, 'password': password}).json()['access']

    def upload(content, extension, token):
        response = http('files/', method='POST', token=token, expected=201,
            files={'file': ('fixture.' + extension, content, 'application/octet-stream')})
        row = response.json()
        if 'data' in row:
            row = row['data']
        source_ids.append(row['id'])
        return row

    def submit(row, token):
        response = http('files/' + row['id'] + '/office-preview/', token=token, method='POST',
            data={'lifecycle_version': row['lifecycle_version']}, expected=202, key=uuid.uuid4().hex)
        job = response.json()['data']
        all_jobs.append(job['id'])
        check('公共任务响应不含令牌和存储位置', set(job) == {'id', 'status', 'error', 'expires_at'})
        return job['id']

    def runner_once():
        verify_ownership(target)
        result = subprocess.run([sys.executable, str(target / 'scripts/office_preview_runner.py'),
            '--image', options.image, '--once'], cwd=target, capture_output=True, timeout=600)
        # Its successful path emits nothing. Failure report is fixed codes/own names only.
        with (evidence / 'runner.log').open('ab') as output:
            output.write(result.stdout + result.stderr)
        check('真实宿主 runner 执行完成', result.returncode == 0)

    def expire(job):
        shell('from apps.files.models import OfficePreview\nfrom django.utils import timezone\n'
            'from datetime import timedelta\nOfficePreview.objects.filter(pk=' + repr(job) +
            ').update(expires_at=timezone.now()-timedelta(seconds=1))\n')
        queue('cleanup')

    try:
        metadata = create_project(target, ref=options.ref, name='admincore-office-' + identifier[:12],
            preset='standard', frontend_port=options.frontend_port, backend_port=options.backend_port)
        created = True
        report.update({'project': metadata['project_name'], 'instance': metadata['instance_id'],
                       'ref': metadata['source_revision']})
        check('导出不包含源环境、Git历史或旧媒体', not (target / '.git').exists()
              and not (target / '.env.admin-access.txt').exists() and not (target / 'backend/media').exists())
        # Only the freshly created environment is read. Never source ROOT/.env.
        environment = target / '.env'
        values = dict(line.split('=', 1) for line in environment.read_text(encoding='utf-8').splitlines()
                      if '=' in line and not line.startswith('#'))
        values.update({'DB_NAME': database, 'ADMINCORE_MODULES': 'files,tasks',
            'ADMINCORE_OFFICE_PREVIEW_ENABLED': 'True', 'ADMINCORE_OFFICE_IMAGE': options.image,
            'ADMINCORE_STORAGE_BACKEND': 'local', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False',
            'AUTH_EMAIL_ENABLED': 'False', 'NOTIFICATION_EMAIL_ENABLED': 'False',
            'ADMINCORE_BACKUP_ENABLED': 'False', 'ALLOW_PUBLIC_REGISTRATION': 'False'})
        environment.write_text('\n'.join(key + '=' + value for key, value in values.items()) + '\n', encoding='utf-8')
        check('构建启动本次独立项目', run_project(target, 'up') == 0)
        shell('assert settings.ADMINCORE_BUILD_PROFILE == "full"\n'
            'from apps.files.office_preview import available\nassert available()\n')
        token = login('admin', values['ADMINCORE_ADMIN_PASSWORD'])
        http('auth/change_password/', token=token, method='POST', data={
            'old_password': values['ADMINCORE_ADMIN_PASSWORD'], 'new_password': new_password,
            'new_password2': new_password})
        token = login('admin', new_password)
        shell('from django.contrib.auth import get_user_model\n'
            'from apps.permissions.models import Role, Permission, RolePermission, UserRole\n'
            'from apps.core.models import DataScopeGrant\n'
            'u=get_user_model().objects.create_user(username=' + repr(member_name) + ', password=' + repr(member_password) + ', must_change_password=False)\n'
            'r=Role.objects.create(name=' + repr('Office fixture ' + identifier[:12]) + ')\n'
            'UserRole.objects.create(user=u, role=r)\n'
            'for code in ("file:upload", "file:download"):\n RolePermission.objects.create(role=r, permission=Permission.objects.get(code=code))\n'
            'DataScopeGrant.objects.create(role=r, resource="file", scope="self")\n')
        member = login(member_name, member_password)
        check('运行时启用 Office', http('files/office-preview/config/', token=token).json()['data']['enabled'])
        fixture_dir = temporary / 'fixtures'
        fixture_dir.mkdir()
        fixtures, proofs = {}, {}
        for odf, ooxml in (('odt', 'docx'), ('ods', 'xlsx'), ('odp', 'pptx')):
            proof = 'ADMINCORE' + odf.upper() + identifier[:8].upper()
            content = odf_fixture(odf, proof)
            path = fixture_dir / ('source.' + odf)
            path.write_bytes(content)
            path.chmod(0o644)
            fixtures[odf], proofs[odf] = content, proof
            fixtures[ooxml] = export_fixture(path, options.image, ooxml, containers)
            proofs[ooxml] = proof
            check('真实 LibreOffice 生成 ' + ooxml + ' 夹具')
        real_pdf = None
        completed_jobs = []
        for extension in ('docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp'):
            row = upload(fixtures[extension], extension, token)
            job = submit(row, token)
            runner_once()
            status = http('files/office-preview/jobs/' + job + '/', token=token).json()['data']
            check(extension + ' 真实转换成功', status['status'] == 'success')
            response = http('files/office-preview/jobs/' + job + '/pdf/', token=token)
            pdf = PdfReader(io.BytesIO(response.content), strict=True)
            text = ''.join(page.extract_text() or '' for page in pdf.pages)
            check(extension + ' PDF 包含实际文档内容', proofs[extension] in ''.join(text.split()))
            check(extension + ' PDF 无外链动作和注解', '/Names' not in pdf.trailer['/Root']
                  and all('/Annots' not in page and '/AA' not in page for page in pdf.pages))
            check(extension + ' PDF 私有禁止缓存', response.headers['Cache-Control'] == 'private, no-store'
                  and response.headers['X-Frame-Options'] == 'DENY')
            http('files/office-preview/jobs/' + job + '/pdf/', expected=401)
            http('files/office-preview/jobs/' + job + '/pdf/', token=member, expected=404)
            real_pdf = response.content
            completed_jobs.append(job)
        check('转换来源仍在且没有派生 FileModel', shell('from apps.files.models import FileModel, OfficePreview\n'
            'assert FileModel.objects.count()==6\n'
            'assert all(f.file.storage.exists(f.file.name) for f in FileModel.objects.all())\n'
            'assert OfficePreview.objects.filter(record__status="success").count()==6\n') is None)

        # Negative completions reuse bytes from an actual successful conversion, never a mock PDF.
        for change in ('permission', 'version', 'sha', 'session', 'cancel', 'lease'):
            row = upload(fixtures['odt'], 'odt', member)
            job = submit(row, member)
            claim = queue('claim')
            check('真实 claim 绑定本任务和源SHA', claim['job_id'] == job
                  and claim['source_sha256'] == hashlib.sha256(fixtures['odt']).hexdigest())
            if change == 'permission':
                shell('from apps.permissions.models import RolePermission\nRolePermission.objects.filter(role__userrole__user__username=' + repr(member_name) + ', permission__code="file:download").delete()\n')
            elif change == 'version':
                shell('from apps.files.models import FileModel\nfrom django.db.models import F\nFileModel.objects.filter(pk=' + repr(row['id']) + ').update(lifecycle_version=F("lifecycle_version")+1)\n')
            elif change == 'sha':
                encoded = base64.b64encode(fixtures['ods']).decode()
                shell('import base64\nfrom apps.files.models import FileModel\nf=FileModel.objects.get(pk=' + repr(row['id']) + ')\nwith f.file.storage.open(f.file.name,"wb") as s:\n s.write(base64.b64decode(' + repr(encoded) + '))\n')
            elif change == 'session':
                http('auth/logout/', token=member, method='POST')
            elif change == 'cancel':
                http('files/office-preview/jobs/' + job + '/', token=member, method='DELETE')
            else:
                shell('from apps.files.models import OfficePreview\nfrom django.utils import timezone\nfrom datetime import timedelta\nOfficePreview.objects.filter(pk=' + repr(job) + ').update(claimed_at=timezone.now()-timedelta(seconds=121))\n')
                queue('cleanup')
            queue('finish', {'job_id': job, 'token': claim['token'],
                'pdf': base64.b64encode(real_pdf).decode()}, expected=1)
            check(change + ' 变化后无法发布结果', shell('from apps.files.models import OfficePreview\nj=OfficePreview.objects.get(pk=' + repr(job) + ')\nassert not j.output_key\n') is None)
            if change == 'permission':
                shell('from apps.permissions.models import RolePermission, Role, Permission\nRolePermission.objects.create(role=Role.objects.get(userrole__user__username=' + repr(member_name) + '), permission=Permission.objects.get(code="file:download"))\n')
            if change == 'session':
                member = login(member_name, member_password)
            expire(job)
            check('失效任务不会重新领取', queue('claim') is None)

        # A new explicit submission is allowed after the old lease is failed; never implicit resume.
        row = upload(fixtures['odt'], 'odt', member)
        retry = submit(row, member)
        runner_once()
        check('失联后仅新的显式任务可以重新转换', http('files/office-preview/jobs/' + retry + '/', token=member).json()['data']['status'] == 'success')
        completed_jobs.append(retry)
        # Replay of a consumed token is covered against a real completed record too.
        row = upload(fixtures['odt'], 'odt', member)
        replay = submit(row, member)
        claim = queue('claim')
        actual_source = temporary / 'single-claim-source.odt'
        actual_source.write_bytes(base64.b64decode(claim['source']))
        actual_source.chmod(0o644)
        try:
            actual_pdf = runner.convert(actual_source, options.image)
        except runner.CleanupFailure as exc:
            containers.add(exc.container)
            raise
        finally:
            actual_source.unlink()
        payload = {'job_id': replay, 'token': claim['token'], 'pdf': base64.b64encode(actual_pdf).decode()}
        queue('finish', payload)
        queue('finish', payload, expected=1)
        completed_jobs.append(replay)
        check('真实单次领取令牌不能重放')
        # History deletion must not orphan output. Delete only this exact owned record.
        shell('from apps.files.models import OfficePreview\nj=OfficePreview.objects.get(pk=' + repr(completed_jobs[0]) + ')\nj.record.delete()\nassert OfficePreview.objects.filter(pk=j.pk, record__isnull=True).exists()\n')
        for job in completed_jobs:
            expire(job)
        shell('from apps.files.models import OfficePreview, FileModel\nfrom django.core.files.storage import default_storage\n'
            'assert not OfficePreview.objects.exclude(output_key="").exists()\n'
            'for ident in ' + repr(all_jobs) + ':\n assert not default_storage.exists("office-preview/"+ident+"/preview.pdf")\n'
            'assert FileModel.objects.count()==' + str(len(source_ids)) + '\n'
            'assert all(f.file.storage.exists(f.file.name) for f in FileModel.objects.all())\n')
        check('全部派生产物已到期清理，原件完整，任务历史删除不遗留文件')
        remaining = list(Path(tempfile.gettempdir()).glob('admincore-office-*'))
        check('成功任务不残留包含源字节的临时目录', not any(
            any(job in folder.name for job in all_jobs) for folder in remaining))
        check('夹具转换器已全部移除', not containers)
        verify_ownership(target)
        command(['down', '-v', '--remove-orphans'])
        report['passed'] = True
    finally:
        if (target / '.codex-validation/project-start.log').is_file():
            shutil.copyfile(target / '.codex-validation/project-start.log', evidence / 'project-start.log')
        if report['passed']:
            if (temporary.parent != Path(tempfile.gettempdir()).resolve()
                    or not temporary.name.startswith('admincore-office-validation-' + identifier + '-')):
                raise RuntimeError('unexpected_cleanup_target')
            shutil.rmtree(temporary)
            report['cleaned'] = ['本次项目容器/卷/网络', str(temporary)]
            report['released_ports'] = [options.frontend_port, options.backend_port]
        else:
            report['retained_fixture'] = str(temporary)
            report['owned_containers_requiring_review'] = sorted(containers)
            if created:
                try:
                    verify_ownership(target)
                    command(['stop'])
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    pass
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(evidence), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
