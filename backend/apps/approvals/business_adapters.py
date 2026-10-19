"""Trusted built-in adapters; generated modules retain their existing registration checks."""
from importlib import import_module

_BUILTINS = {'online_forms': 'apps.online_forms.approval_integration'}


def _adapter(application):
    path = _BUILTINS.get(application.business_module, 'apps.core.codegen.integrations')
    return import_module(path)


def sync_approval(application, request):
    return _adapter(application).sync_approval(application, request)


def redact_approval_snapshot(application, actor, data, *, read_snapshot=None):
    return _adapter(application).redact_approval_snapshot(application, actor, data, read_snapshot=read_snapshot)
