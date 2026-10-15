from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CallbackView, CancelView, CompleteView, ConfigView, IdentityViewSet, StartView, StatusView

router = SimpleRouter()
router.register('identities', IdentityViewSet, basename='sso-identity')
urlpatterns = [path('config/', ConfigView.as_view()), path('start/', StartView.as_view()),
               path('callback/', CallbackView.as_view()), path('status/', StatusView.as_view()),
               path('complete/', CompleteView.as_view()), path('cancel/', CancelView.as_view()), *router.urls]
