"""
Root URL configuration.

There is no django.contrib.admin route: the admin site is not installed, since
this is a JSON API and the admin requires the is_staff/is_superuser fields the
assessment's User table does not define.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from rides.views import RideEventViewSet, RideViewSet
from users.views import ObtainAuthTokenView, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("rides", RideViewSet)
router.register("ride-events", RideEventViewSet)

urlpatterns = [
    path("api/auth/token/", ObtainAuthTokenView.as_view(), name="obtain-token"),
    path("api/", include(router.urls)),
]
