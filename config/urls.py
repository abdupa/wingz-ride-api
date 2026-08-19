"""
Root URL configuration.

The API router is registered here once the ViewSets exist. There is no
django.contrib.admin route: the admin site is not installed, since this is a
JSON API and the admin requires the is_staff/is_superuser fields that the
assessment's User table does not define.
"""

urlpatterns = []
