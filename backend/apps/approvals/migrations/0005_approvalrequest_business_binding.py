from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('approvals', '0004_protect_approval_participants')]
    operations = [
        migrations.AddField(model_name='approvalrequest', name='business_module', field=models.CharField(max_length=20, blank=True)),
        migrations.AddField(model_name='approvalrequest', name='business_record_id', field=models.UUIDField(null=True, blank=True)),
        migrations.AddField(model_name='approvalrequest', name='business_snapshot', field=models.JSONField(default=dict, blank=True)),
    ]
