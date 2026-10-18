import uuid

import django.db.models.deletion
from django.db import migrations, models


def protect_legacy_snapshots(apps, schema_editor):
    """旧快照没保存字段类型；只保护其值恰好指向同租户现存普通文件的 UUID。

    不依赖当前生成 schema（字段可能已删除/重命名）；保守保护可能多于实际附件，
    不推断路径、不修改快照、不恢复已删除存储。不向其他租户建立引用。
    """
    alias = schema_editor.connection.alias
    requests = apps.get_model('approvals', 'ApprovalRequest').objects.using(alias)
    files = apps.get_model('files', 'FileModel').objects.using(alias)
    references = apps.get_model('approvals', 'ApprovalFileReference').objects.using(alias)
    for application in requests.exclude(business_module='').iterator(chunk_size=200):
        snapshot = application.business_snapshot
        if not isinstance(snapshot, dict):
            continue
        rows = [snapshot.get('fields')]
        details = snapshot.get('details')
        if isinstance(details, dict):
            for group in details.values():
                if isinstance(group, list):
                    rows.extend(group)
        identifiers = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            for value in row.values():
                if isinstance(value, str) and len(value) in (32, 36):
                    try:
                        identifiers.add(uuid.UUID(value))
                    except ValueError:
                        pass
        ordered = sorted(identifiers)
        for offset in range(0, len(ordered), 250):
            matched = files.filter(pk__in=ordered[offset:offset + 250], tenant_id=application.tenant_id, purpose='general')
            references.bulk_create([
                references.model(request_id=application.pk, file_id=identifier, tenant_id=application.tenant_id)
                for identifier in matched.values_list('pk', flat=True)
            ], batch_size=200)


class Migration(migrations.Migration):
    dependencies = [
        ('approvals', '0007_remove_approvalstep_unique_approval_step_assignee_and_more'),
        ('files', '0009_fileaccessgrant'),
    ]
    operations = [
        migrations.CreateModel(
            name='ApprovalFileReference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='%(app_label)s_%(class)s_records', to='core.tenant', verbose_name='租户')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='file_references', to='approvals.approvalrequest')),
                ('file', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='approval_references', to='files.filemodel')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('request', 'file'), name='unique_approval_file_reference')],
            },
        ),
        migrations.RunPython(protect_legacy_snapshots, migrations.RunPython.noop),
    ]
