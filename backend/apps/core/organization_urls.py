from rest_framework.routers import DefaultRouter
from django.urls import path
from .organization_views import DepartmentViewSet, MembershipViewSet, ScopeGrantViewSet
from .post_views import PostViewSet, UserPostViewSet, PersonnelView, PersonnelDepartmentsView

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='department')
router.register('memberships', MembershipViewSet, basename='membership')
router.register('scopes', ScopeGrantViewSet, basename='data-scope')
router.register('posts', PostViewSet, basename='post')
router.register('user-posts', UserPostViewSet, basename='user-post')
urlpatterns = [path('people/', PersonnelView.as_view()), path('people/departments/', PersonnelDepartmentsView.as_view()), *router.urls]
