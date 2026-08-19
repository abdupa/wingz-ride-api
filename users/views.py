from rest_framework import viewsets

from .models import User
from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """Full CRUD over the assessment's User table."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
