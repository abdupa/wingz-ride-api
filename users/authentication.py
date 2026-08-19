from django.contrib.auth import authenticate
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class EmailAuthTokenSerializer(serializers.Serializer):
    """
    DRF's stock token serializer asks for a field called "username". This one
    asks for an email, because that is what USERNAME_FIELD is here and a
    parameter named "username" holding an email address is a small lie the
    README would then have to explain.
    """

    email = serializers.EmailField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, write_only=True
    )

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].lower(),
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError(
                {"detail": "Unable to log in with the credentials provided."}
            )
        attrs["user"] = user
        return attrs


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
