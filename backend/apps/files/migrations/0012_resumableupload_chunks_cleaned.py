from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('files', '0011_filecapacity_filedocument_filerevision')]
    operations = [migrations.AddField(
        model_name='resumableupload', name='chunks_cleaned',
        field=models.BooleanField(default=False),
    )]
