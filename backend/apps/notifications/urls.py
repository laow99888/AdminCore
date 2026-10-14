"""
通知系统 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet
from .announcement_views import AnnouncementPublicViewSet, AnnouncementManageViewSet

router = DefaultRouter()
router.register(r'announcements/manage', AnnouncementManageViewSet, basename='announcement-management')
router.register(r'announcements', AnnouncementPublicViewSet, basename='announcement')
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
