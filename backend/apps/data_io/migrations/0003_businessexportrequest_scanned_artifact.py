from django.db import migrations
from apps.files.fields import ScannedFileField


class Migration(migrations.Migration):
    dependencies = [('data_io', '0002_businessexportrequest')]
    operations = [migrations.AlterField(
        model_name='businessexportrequest', name='artifact',
        field=ScannedFileField(upload_to='private-business-exports/%Y/%m/%d/', blank=True),
    )]
