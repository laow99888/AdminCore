from django.apps import AppConfig


class APICredentialsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api_credentials'
    verbose_name = '开放凭证'

    def ready(self):
        from . import schema  # noqa: F401
