"""已有表反射必须匹配生成模型的用户/租户边界。"""
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model

from apps.core.codegen import tables
from apps.core.codegen.spec import GenerationError


def reflected_table(monkeypatch, *, tenant_column=('uuid', 'YES', None), tenant_target=('core_tenant', 'id'), extra=False):
    columns = [
        ('id', 'uuid', 'NO', None), ('creator_id', 'uuid', 'NO', None),
        ('version', 'integer', 'NO', None),
        ('created_at', 'timestamp with time zone', 'NO', None),
        ('updated_at', 'timestamp with time zone', 'NO', None),
        ('label', 'character varying', 'NO', 80),
    ]
    if tenant_column is not None:
        columns.append(('tenant_id', *tenant_column))
    user = get_user_model()._meta
    constraints = {
        'pk': {'columns': ['id'], 'primary_key': True},
        'creator': {'columns': ['creator_id'], 'foreign_key': (user.db_table, user.pk.column)},
        'tenant': {'columns': ['tenant_id'], 'foreign_key': tenant_target},
    }
    if extra:
        constraints['other'] = {'columns': ['other_id'], 'foreign_key': ('business_other', 'id')}
    cursor = MagicMock()
    cursor.fetchone.side_effect = [('r', False, False, False), (False,)]
    cursor.fetchall.side_effect = [columns, [('a',), ('a',)], [('CHECK (version >= 1)',)]]
    connection = MagicMock(vendor='postgresql')
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.introspection.get_constraints.return_value = constraints
    monkeypatch.setattr(tables, 'connection', connection)


def test_existing_table_accepts_only_platform_relationships(monkeypatch):
    reflected_table(monkeypatch)
    definition = tables.inspect_table('business_records', 'business_records', 'BusinessRecord', '记录')
    assert [field['name'] for field in definition['fields']] == ['label']


@pytest.mark.parametrize('options', [
    {'tenant_column': None},
    {'tenant_column': ('uuid', 'NO', None)},
    {'tenant_column': ('integer', 'YES', None)},
    {'tenant_target': ('auth_app_user', 'id')},
    {'tenant_target': None},
    {'extra': True},
])
def test_existing_table_rejects_missing_or_foreign_tenant_boundary(monkeypatch, options):
    reflected_table(monkeypatch, **options)
    with pytest.raises(GenerationError):
        tables.inspect_table('business_records', 'business_records', 'BusinessRecord', '记录')
