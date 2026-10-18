from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CredentialViewSet, TaskGatewayViewSet, WorkItemGatewayViewSet
from .business_views import BusinessGatewayViewSet
from .service_views import ServiceIdentityViewSet

router = DefaultRouter()
router.register('credentials', CredentialViewSet, basename='api-credential')
router.register('service-identities', ServiceIdentityViewSet, basename='service-identity')
router.register('tasks', TaskGatewayViewSet, basename='api-gateway-task')
router.register('work-items', WorkItemGatewayViewSet, basename='api-gateway-work-item')
urlpatterns = [
    path('business/<slug:resource>/records/', BusinessGatewayViewSet.as_view({'get': 'list'}), name='api-business-list'),
    path('business/<slug:resource>/records/<uuid:pk>/', BusinessGatewayViewSet.as_view({'get': 'retrieve'}), name='api-business-detail'),
    path('', include(router.urls)),
]
