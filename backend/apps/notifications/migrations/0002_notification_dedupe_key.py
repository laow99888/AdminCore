from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('notifications', '0001_initial')]
    operations = [migrations.AddField(model_name='notification', name='dedupe_key', field=models.CharField(blank=True, max_length=180, null=True, unique=True, verbose_name='事件去重键'))]
