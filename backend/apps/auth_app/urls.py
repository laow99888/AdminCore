"""
认证应用 URL 配置
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomTokenObtainPairView, AuthViewSet
from .session_views import PersonalSessionViewSet, OnlineUserViewSet
from .recovery_views import (RecoveryConfigView, RecoveryRequestView, RecoveryResetView,
                             VerificationRequestView, VerificationConfirmView)

router = DefaultRouter()
router.register(r'sessions', PersonalSessionViewSet, basename='personal-sessions')
router.register(r'online-users', OnlineUserViewSet, basename='online-users')
router.register(r'', AuthViewSet, basename='auth')

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('recovery/config/', RecoveryConfigView.as_view(), name='recovery-config'),
    path('recovery/request/', RecoveryRequestView.as_view(), name='recovery-request'),
    path('recovery/reset/', RecoveryResetView.as_view(), name='recovery-reset'),
    path('email-verification/request/', VerificationRequestView.as_view(), name='email-verification-request'),
    path('email-verification/confirm/', VerificationConfirmView.as_view(), name='email-verification-confirm'),
    path('', include(router.urls)),
]
