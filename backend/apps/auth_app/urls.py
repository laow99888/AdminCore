"""
认证应用 URL 配置
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomTokenObtainPairView, AuthViewSet
from .session_views import PersonalSessionViewSet, OnlineUserViewSet
from .recovery_views import (RecoveryConfigView, RecoveryRequestView, RecoveryResetView,
                             VerificationRequestView, VerificationConfirmView)
from .totp_views import TOTPView, TOTPSetupView, TOTPChangeView, TOTPDisableView, TOTPRecoveryCodesView
from .captcha_views import LoginCaptchaView

router = DefaultRouter()
router.register(r'sessions', PersonalSessionViewSet, basename='personal-sessions')
router.register(r'online-users', OnlineUserViewSet, basename='online-users')
router.register(r'', AuthViewSet, basename='auth')

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login-captcha/', LoginCaptchaView.as_view(), name='login-captcha'),
    path('recovery/config/', RecoveryConfigView.as_view(), name='recovery-config'),
    path('recovery/request/', RecoveryRequestView.as_view(), name='recovery-request'),
    path('recovery/reset/', RecoveryResetView.as_view(), name='recovery-reset'),
    path('email-verification/request/', VerificationRequestView.as_view(), name='email-verification-request'),
    path('email-verification/confirm/', VerificationConfirmView.as_view(), name='email-verification-confirm'),
    path('totp/', TOTPView.as_view(), name='totp-status'),
    path('totp/setup/', TOTPSetupView.as_view(), name='totp-setup'),
    path('totp/enable/', TOTPChangeView.as_view(), name='totp-enable'),
    path('totp/disable/', TOTPDisableView.as_view(), name='totp-disable'),
    path('totp/recovery-codes/', TOTPRecoveryCodesView.as_view(), name='totp-recovery-codes'),
    path('', include(router.urls)),
]
