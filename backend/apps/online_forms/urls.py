from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FormRecordViewSet, OnlineFormViewSet, PublishedFormView, FormValidationView, FormApprovalChoicesView
from .attachment_views import FormAttachmentView
from .relation_views import FormRelationView, FormRelationResourcesView

router = DefaultRouter()
router.register('forms', OnlineFormViewSet, basename='online-form')
urlpatterns = [
    path('relation-resources/', FormRelationResourcesView.as_view(), name='online-form-relation-resources'),
    path('approval-flows/', FormApprovalChoicesView.as_view(), name='online-form-approval-choices'),
    path('validate/', FormValidationView.as_view(), name='online-form-validate'),
    path('published/<slug:code>/', PublishedFormView.as_view(), name='online-form-published'),
    path('<slug:code>/attachments/', FormAttachmentView.as_view(), name='online-form-attachments'),
    path('<slug:code>/relations/', FormRelationView.as_view(), name='online-form-relations'),
    path('<slug:code>/records/', FormRecordViewSet.as_view({'get': 'list', 'post': 'create'}), name='online-form-record-list'),
    path('<slug:code>/records/<uuid:pk>/', FormRecordViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}), name='online-form-record-detail'),
    path('<slug:code>/records/<uuid:pk>/submit-approval/', FormRecordViewSet.as_view({'post': 'submit_approval'}), name='online-form-record-submit'),
    path('<slug:code>/records/<uuid:pk>/withdraw-approval/', FormRecordViewSet.as_view({'post': 'withdraw_approval'}), name='online-form-record-withdraw'),
    path('', include(router.urls)),
]
