from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("auth/apple/", views.AppleSignInView.as_view(), name="auth-apple"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", views.MeView.as_view(), name="me"),
]
