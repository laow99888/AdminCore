from django.apps import AppConfig


class FeatureFlagsConfig(AppConfig):
    name = 'apps.feature_flags'
    verbose_name = '特性开关'
    default_auto_field = 'django.db.models.BigAutoField'
