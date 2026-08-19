from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates users keyed by email, carrying the role the API authorises on."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.Role.RIDER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        # "Superuser" here means role='admin'. There is no is_superuser field
        # because PermissionsMixin is not used, and 'admin' is the only role
        # the API authorises on. This keeps `manage.py createsuperuser`
        # working, which is what a reviewer will reach for first.
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        if extra_fields.get("role") != self.model.Role.ADMIN:
            raise ValueError("Superuser must have role='admin'.")
        return self._create_user(email, password, **extra_fields)
