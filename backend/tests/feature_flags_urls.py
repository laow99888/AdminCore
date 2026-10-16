from django.urls import include, path
from config.urls import urlpatterns as base_patterns

urlpatterns = [*base_patterns, path('api/v1/feature-flags/', include('apps.feature_flags.urls'))]
