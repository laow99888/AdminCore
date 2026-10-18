from rest_framework.routers import DefaultRouter
from django.urls import path
from .organization_views import DepartmentViewSet, MembershipViewSet, ScopeGrantViewSet
from .appointment_views import AppointmentViewSet
from .post_views import PostViewSet, UserPostViewSet, PersonnelView, PersonnelDepartmentsView
from .tenant_views import TenantViewSet, TenantMembershipViewSet, MyTenantView

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='department')
router.register('memberships', MembershipViewSet, basename='membership')
router.register('appointments', AppointmentViewSet, basename='appointment')
router.register('scopes', ScopeGrantViewSet, basename='data-scope')
router.register('posts', PostViewSet, basename='post')
router.register('user-posts', UserPostViewSet, basename='user-post')
router.register('tenants', TenantViewSet, basename='tenant')
router.register('tenant-memberships', TenantMembershipViewSet, basename='tenant-membership')
urlpatterns = [path('people/', PersonnelView.as_view()), path('people/departments/', PersonnelDepartmentsView.as_view()),
               path('my-tenants/', MyTenantView.as_view({'get': 'list'})), *router.urls]
