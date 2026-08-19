from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class User(AbstractBaseUser):
    """
    The assessment's User table.

    AbstractBaseUser adds `password` and `last_login`. That is the one
    deliberate deviation from the spec's table definition: requirement 2
    demands authentication, and the table as specified holds nothing to
    authenticate with.

    PermissionsMixin is deliberately not used. It would add is_staff,
    is_superuser and two join tables for groups and permissions, none of
    which this API uses -- its only authorisation rule is role == 'admin'.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        RIDER = "rider", "Rider"
        DRIVER = "driver", "Driver"

    id_user = models.AutoField(primary_key=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RIDER)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254, unique=True)
    phone_number = models.CharField(max_length=32)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "phone_number"]

    objects = UserManager()

    class Meta:
        db_table = "user"
        ordering = ["id_user"]
        indexes = [models.Index(fields=["role"], name="user_role_idx")]
        constraints = [
            # save() lowercases the email, but save() is not the only way a row
            # gets written -- bulk_create, queryset.update() and raw SQL all
            # bypass it, silently storing a value the email filter can never
            # match. The invariant belongs where nothing can dodge it.
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")),
                name="user_email_is_lowercase",
            ),
        ]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def save(self, *args, **kwargs):
        # Normalised at write time so email lookups can use the unique index.
        # Matching case-insensitively at read time (iexact) compiles to
        # UPPER(email) = ... which cannot use that index.
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN
