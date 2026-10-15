from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CredentialViewSet, TaskGatewayViewSet, WorkItemGatewayViewSet

router = DefaultRouter()
router.register('credentials', CredentialViewSet, basename='api-credential')
router.register('tasks', TaskGatewayViewSet, basename='api-gateway-task')
router.register('work-items', WorkItemGatewayViewSet, basename='api-gateway-work-item')
urlpatterns = [path('', include(router.urls))]
