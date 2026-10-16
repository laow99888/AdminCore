from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('permissions', '0004_menu_tenant_permission_tenant_role_tenant_and_more')]

    operations = [
        migrations.AddField(
            model_name='role',
            name='field_permissions',
            field=models.JSONField(blank=True, default=dict, verbose_name='字段权限策略'),
        ),
    ]
