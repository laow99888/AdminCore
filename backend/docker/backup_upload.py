"""独立私有 S3 备份目标；流式上传后重新读取校验，清单最后发布。"""
import hashlib
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit


def upload(stamp, name, expected, size, source):
    bucket = os.getenv('ADMINCORE_BACKUP_S3_BUCKET', '')
    if not bucket:
        return {'remote_copy': False}
    prefix = os.getenv('ADMINCORE_BACKUP_S3_PREFIX', 'admincore-backups')
    endpoint = os.getenv('ADMINCORE_BACKUP_S3_ENDPOINT', '')
    if (not re.fullmatch(r'\d{8}-\d{6}', stamp)
            or name not in (f'admincore-db-{stamp}.dump', f'admincore-media-{stamp}.tar.gz', f'admincore-{stamp}.sha256')
            or not re.fullmatch(r'[0-9a-f]{64}', expected) or type(size) is not int or size < 0
            or not prefix or any(part in ('', '.', '..') for part in prefix.split('/'))
            or '\\' in prefix or ':' in prefix or any(ord(char) < 32 for char in prefix)):
        raise ValueError('invalid_backup_parameters')
    if endpoint:
        url = urlsplit(endpoint)
        insecure = os.getenv('ADMINCORE_BACKUP_S3_ALLOW_HTTP', 'False').lower() == 'true'
        if (url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password
                or url.path not in ('', '/') or url.query or url.fragment or (url.scheme == 'http' and not insecure)):
            raise ValueError('invalid_backup_endpoint')
    access = os.getenv('ADMINCORE_BACKUP_S3_ACCESS_KEY', '')
    secret = os.getenv('ADMINCORE_BACKUP_S3_SECRET_KEY', '')
    if not access or not secret:
        raise ValueError('missing_backup_credentials')
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    client = boto3.client('s3', endpoint_url=endpoint or None, aws_access_key_id=access,
                          aws_secret_access_key=secret, region_name=os.getenv('ADMINCORE_BACKUP_S3_REGION', 'us-east-1'),
                          config=Config(connect_timeout=10, read_timeout=30, retries={'max_attempts': 3},
                                        s3={'addressing_style': 'path'}))
    # 每个对象请求 private ACL；桶策略/公共访问阻止由部署者配置并验收。
    key = f'{prefix}/{stamp}/{name}'
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if str(exc.response.get('Error', {}).get('Code')) not in ('404', 'NoSuchKey', 'NotFound'):
            raise
    else:
        raise ValueError('backup_target_exists')
    checksum, total = hashlib.sha256(), 0
    with tempfile.TemporaryFile() as temporary:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            total += len(chunk)
            if total > size:
                raise ValueError('backup_size_mismatch')
            checksum.update(chunk)
            temporary.write(chunk)
        if total != size or checksum.hexdigest() != expected:
            raise ValueError('backup_checksum_mismatch')
        temporary.seek(0)
        client.upload_fileobj(temporary, bucket, key, ExtraArgs={'Metadata': {'sha256': expected}, 'ACL': 'private'})
    response = client.get_object(Bucket=bucket, Key=key)
    checksum, total = hashlib.sha256(), 0
    try:
        for chunk in iter(lambda: response['Body'].read(1024 * 1024), b''):
            checksum.update(chunk)
            total += len(chunk)
    finally:
        response['Body'].close()
    if total != size or checksum.hexdigest() != expected:
        raise ValueError('remote_backup_checksum_mismatch')
    return {'remote_copy': True}


if __name__ == '__main__':
    try:
        print(json.dumps(upload(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.stdin.buffer)))
    except Exception:
        # SDK 异常可能包含 endpoint/签名信息；不把异常或凭据写进日志。
        print('独立备份副本上传或校验失败', file=sys.stderr)
        raise SystemExit(1)
