from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import EmailAuthTokenSerializer, UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """Full CRUD over the assessment's User table."""

    queryset = User.objects.all()
    serializer_class = UserSerializer


class ObtainAuthTokenView(APIView):
    """
    Exchanges an email and password for a token.

    This endpoint must be open. The permission class is applied globally, so
    without this exemption you would need an admin token in order to obtain an
    admin token, and nobody could ever authenticate.

    It authenticates any valid user, not only admins. Proving who you are and
    being allowed in are separate questions -- a non-admin gets a perfectly
    valid token that opens no doors.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailAuthTokenSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        token, _ = Token.objects.get_or_create(user=serializer.validated_data["user"])
        return Response({"token": token.key}, status=status.HTTP_200_OK)
