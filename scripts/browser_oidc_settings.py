"""仅复制到隔离验收派生镜像；生产代码不添加可配置的回环豁免。"""
from config.settings.production import *

if DATABASES['default']['NAME'] != 'browser_session_fixture':
    raise RuntimeError('OIDC fixture settings require an isolated browser database')

TESTING = True
SSO_TEST_ALLOW_LOOPBACK = True
