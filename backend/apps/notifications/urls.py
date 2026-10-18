"""
通知系统 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet
from .announcement_views import AnnouncementPublicViewSet, AnnouncementManageViewSet
from .message_views import MessageTemplateViewSet, MessageDeliveryViewSet
from .preference_views import NotificationPreferenceView
from .digest_views import (BusinessNoticeView, DigestDetailView, DigestRefreshView, DigestStatusView,
                           NotificationOperationsView)

router = DefaultRouter()
router.register(r'templates', MessageTemplateViewSet, basename='message-template')
router.register(r'deliveries', MessageDeliveryViewSet, basename='message-delivery')
router.register(r'announcements/manage', AnnouncementManageViewSet, basename='announcement-management')
router.register(r'announcements', AnnouncementPublicViewSet, basename='announcement')
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('digests/status/', DigestStatusView.as_view(), name='notification-digest-status'),
    path('digests/refresh/', DigestRefreshView.as_view(), name='notification-digest-refresh'),
    path('digests/<uuid:notification_id>/', DigestDetailView.as_view(), name='notification-digest-detail'),
    path('business-notices/', BusinessNoticeView.as_view(), name='business-notice-submit'),
    path('operations/', NotificationOperationsView.as_view(), name='notification-operations'),
    path('', include(router.urls)),
]
