import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [('tasks', '0006_backup_runner_status_restore_request')]
    operations = [migrations.CreateModel(
        name='BackupPreflight',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('timestamp', models.CharField(max_length=15)),
            ('artifact_digest', models.CharField(max_length=64)),
            ('expires_at', models.DateTimeField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ],
    )]
