from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FormRecordViewSet, OnlineFormViewSet, PublishedFormView

router = DefaultRouter()
router.register('forms', OnlineFormViewSet, basename='online-form')
urlpatterns = [
    path('published/<slug:code>/', PublishedFormView.as_view(), name='online-form-published'),
    path('<slug:code>/records/', FormRecordViewSet.as_view({'get': 'list', 'post': 'create'}), name='online-form-record-list'),
    path('<slug:code>/records/<uuid:pk>/', FormRecordViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='online-form-record-detail'),
    path('', include(router.urls)),
]
