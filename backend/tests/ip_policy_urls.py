from django.urls import include, path
from config.urls import urlpatterns as core_patterns

urlpatterns = [path('api/v1/ip-policy/', include('apps.ip_policy.urls')), *core_patterns]
