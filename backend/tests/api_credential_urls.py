from django.urls import include, path

urlpatterns = [
    path('api/v1/auth/', include('apps.auth_app.urls')),
    path('api/v1/tasks/', include('apps.tasks.urls')),
    path('api/v1/api-credentials/', include('apps.api_credentials.urls')),
]
