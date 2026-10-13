from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .system_views import SystemConfigView, SystemConfigListView, DictionaryViewSet

router = DefaultRouter()
router.register('dictionaries', DictionaryViewSet, basename='dictionary')
urlpatterns = [path('config/', SystemConfigListView.as_view()),
               path('config/<str:key>/', SystemConfigView.as_view()), path('', include(router.urls))]
