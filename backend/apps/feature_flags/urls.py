from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import FeatureFlagViewSet, EvaluateView, TargetsView


router = DefaultRouter()
router.register('flags', FeatureFlagViewSet, basename='feature-flag')
urlpatterns = [path('evaluate/', EvaluateView.as_view(), name='feature-flag-evaluate'),
               path('targets/', TargetsView.as_view(), name='feature-flag-targets'), *router.urls]
