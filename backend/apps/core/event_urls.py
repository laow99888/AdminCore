from rest_framework.routers import DefaultRouter
from .event_views import OutboxEventViewSet

router = DefaultRouter()
router.register('events', OutboxEventViewSet, basename='outbox-event')
urlpatterns = router.urls
