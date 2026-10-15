from django.urls import include, path

urlpatterns = [path('api/v1/sso/', include('apps.sso.urls')), path('', include('config.urls'))]
