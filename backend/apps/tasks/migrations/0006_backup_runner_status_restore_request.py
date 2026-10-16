import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('tasks', '0005_maintenancerequest_policy_and_more')]
    operations = [
        migrations.CreateModel(
            name='BackupRunnerStatus',
            fields=[
                ('key', models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ('state', models.CharField(default='offline', max_length=20)),
                ('directory_label', models.CharField(blank=True, max_length=200)),
                ('stage', models.CharField(blank=True, max_length=40)),
                ('last_error', models.CharField(blank=True, max_length=200)),
                ('artifacts', models.JSONField(default=list)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='BackupRestoreRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.CharField(max_length=15)),
                ('preflight_id', models.UUIDField()),
                ('status', models.CharField(choices=[('pending', '等待执行'), ('running', '执行中'), ('succeeded', '成功'), ('failed', '失败'), ('unknown', '结果待核对')], default='pending', max_length=20)),
                ('error', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('requested_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='backup_restore_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['status', 'created_at'], name='tasks_backu_status_3f2a8e_idx'), models.Index(fields=['timestamp', 'created_at'], name='tasks_backu_timesta_0f1e48_idx')]},
        ),
    ]
