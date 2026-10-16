from django.urls import path
from .views import PolicyView, PreviewView

urlpatterns = [path('', PolicyView.as_view()), path('preview/', PreviewView.as_view())]
