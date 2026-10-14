"""
认证应用 URL 配置
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomTokenObtainPairView, AuthViewSet
from .session_views import PersonalSessionViewSet, OnlineUserViewSet

router = DefaultRouter()
router.register(r'sessions', PersonalSessionViewSet, basename='personal-sessions')
router.register(r'online-users', OnlineUserViewSet, basename='online-users')
router.register(r'', AuthViewSet, basename='auth')

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('', include(router.urls)),
]
