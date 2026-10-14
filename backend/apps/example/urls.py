from rest_framework.routers import DefaultRouter
from .views import WorkItemViewSet

router = DefaultRouter()
router.register('items', WorkItemViewSet, basename='example-item')
urlpatterns = router.urls
