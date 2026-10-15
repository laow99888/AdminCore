import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0010_alter_user_phone'),
        ('files', '0004_alter_filemodel_purpose'),
        ('tasks', '0005_maintenancerequest_policy_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OfficePreview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('session_version', models.PositiveIntegerField()),
                ('source_version', models.PositiveIntegerField()),
                ('source_sha256', models.CharField(max_length=64)),
                ('engine', models.CharField(max_length=255)),
                ('claim_digest', models.CharField(blank=True, max_length=64)),
                ('claimed_at', models.DateTimeField(null=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('output_key', models.CharField(blank=True, max_length=255)),
                ('output_sha256', models.CharField(blank=True, max_length=64)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('record', models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='office_preview', to='tasks.taskrecord')),
                ('session', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth_app.authsession')),
                ('source', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='files.filemodel')),
            ],
            options={
                'indexes': [models.Index(fields=['actor', 'created_at'], name='office_actor_created_idx')],
            },
        ),
    ]
