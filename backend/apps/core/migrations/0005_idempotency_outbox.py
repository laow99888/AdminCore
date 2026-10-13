import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0004_organizationmembership_version'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='IdempotencyRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('scope', models.CharField(max_length=120)), ('key', models.CharField(max_length=128)),
                ('request_hash', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('pending', '处理中'), ('succeeded', '已完成')], default='pending', max_length=20)),
                ('response_status', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('response_data', models.JSONField(blank=True, null=True)), ('expires_at', models.DateTimeField()),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='idempotency_records', to=settings.AUTH_USER_MODEL)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('actor', 'scope', 'key'), name='unique_idempotency_actor_scope_key')],
                     'ordering': ['-created_at'],
                     'indexes': [models.Index(fields=('status', 'expires_at'), name='core_idempo_status_c49166_idx')]},
        ),
        migrations.CreateModel(
            name='OutboxEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('topic', models.CharField(max_length=120)), ('event_key', models.CharField(max_length=180, unique=True)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', '待派发'), ('succeeded', '已完成'), ('failed', '失败')], default='pending', max_length=20)),
                ('attempts', models.PositiveIntegerField(default=0)), ('available_at', models.DateTimeField()),
                ('last_error', models.TextField(blank=True)), ('request_id', models.CharField(blank=True, max_length=100)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=('status', 'available_at'), name='core_outbox_status_68cde3_idx'), models.Index(fields=('topic', 'created_at'), name='core_outbox_topic_3b6c99_idx')]},
        ),
    ]
