from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReportCatalogView, ReportViewSet

router = DefaultRouter()
router.register('definitions', ReportViewSet, basename='report-definition')
urlpatterns = [path('catalog/', ReportCatalogView.as_view(), name='report-catalog'), path('', include(router.urls))]
