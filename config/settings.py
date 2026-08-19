"""
Django settings for the Wingz ride API.

Configuration comes from the environment so the same code runs locally and in
CI without edits. Copy .env.example to .env to get started.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# django.contrib.admin is deliberately absent. This is a JSON API, and the
# admin site requires the is_staff/is_superuser fields that PermissionsMixin
# adds -- fields the assessment's User table does not define.
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "users",
    "rides",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db()}

# Set before the first migration is ever run. Changing AUTH_USER_MODEL after
# migrating means dropping the database, which is why the custom user model
# is the first thing built.
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

# UTC keeps the bonus SQL report's month boundaries deterministic. to_char()
# on a timestamptz formats in the session timezone, so a trip at 23:30 on the
# last of the month could otherwise land in either month.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    # Token first, and the order matters. DRF picks 401 vs 403 for an
    # unauthenticated request from the FIRST authentication class: token auth
    # sends a WWW-Authenticate header and yields 401, session auth sends none
    # and yields 403. Listing session first would make every anonymous request
    # return the wrong status code.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Closed by default, so a ViewSet added later cannot be left open by
    # forgetting to protect it. The token endpoint opts out explicitly.
    "DEFAULT_PERMISSION_CLASSES": [
        "users.permissions.IsAdminRole",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.CappedPageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "config.ordering.StrictOrderingFilter",
    ],
}

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
