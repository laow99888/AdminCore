from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .system_views import SystemConfigView, SystemConfigListView, DictionaryViewSet
from .diagnostic_views import InformationView, MonitorView

router = DefaultRouter()
router.register('dictionaries', DictionaryViewSet, basename='dictionary')
urlpatterns = [path('information/', InformationView.as_view()), path('monitor/', MonitorView.as_view()),
               path('config/', SystemConfigListView.as_view()),
               path('config/<str:key>/', SystemConfigView.as_view()), path('', include(router.urls))]
