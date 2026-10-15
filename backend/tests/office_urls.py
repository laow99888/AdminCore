from django.urls import include, path

urlpatterns = [path('api/v1/auth/', include('apps.auth_app.urls')),
               path('api/v1/files/', include('apps.files.urls'))]
