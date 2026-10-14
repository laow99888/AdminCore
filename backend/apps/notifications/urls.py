"""
通知系统 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet
from .announcement_views import AnnouncementPublicViewSet, AnnouncementManageViewSet
from .message_views import MessageTemplateViewSet, MessageDeliveryViewSet

router = DefaultRouter()
router.register(r'templates', MessageTemplateViewSet, basename='message-template')
router.register(r'deliveries', MessageDeliveryViewSet, basename='message-delivery')
router.register(r'announcements/manage', AnnouncementManageViewSet, basename='announcement-management')
router.register(r'announcements', AnnouncementPublicViewSet, basename='announcement')
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
