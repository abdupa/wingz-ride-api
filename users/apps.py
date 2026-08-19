from django.apps import AppConfig


class UsersConfig(AppConfig):
    # AutoField, not BigAutoField: the spec's table definitions say INT.
    default_auto_field = "django.db.models.AutoField"
    name = "users"
