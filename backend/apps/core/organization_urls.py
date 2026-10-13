from rest_framework.routers import DefaultRouter
from .organization_views import DepartmentViewSet, MembershipViewSet, ScopeGrantViewSet

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='department')
router.register('memberships', MembershipViewSet, basename='membership')
router.register('scopes', ScopeGrantViewSet, basename='data-scope')
urlpatterns = router.urls
