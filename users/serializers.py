from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Fields are declared in the order the assessment's User table lists them.
    The physical column order cannot match -- AbstractBaseUser's inherited
    password and last_login are emitted first by Django -- but the JSON a
    reviewer actually reads can, and does.

    password is write-only. Riders and drivers never authenticate, so it is
    optional: created without one, an account gets an unusable password and
    simply cannot log in.
    """

    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "id_user",
            "role",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


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
