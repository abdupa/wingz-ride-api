from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """
    DRF's handler, plus the database-level errors it does not know about.

    DRF turns its own exceptions into responses and lets everything else become
    a 500. ProtectedError is raised by Django, not DRF -- so deleting a user who
    still has rides, a case the PROTECT foreign key deliberately creates,
    surfaced as an unhandled server error.

    409 rather than 400: the request is perfectly well formed, it just conflicts
    with the current state of the data.
    """
    if isinstance(exc, ProtectedError):
        referencing = len(getattr(exc, "protected_objects", ()) or ())
        return Response(
            {
                "detail": (
                    "This record cannot be deleted because "
                    f"{referencing} other record(s) reference it."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )
    return drf_exception_handler(exc, context)
