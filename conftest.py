import pytest
from django.utils import timezone

from rides.models import Ride, RideEvent
from users.models import User


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email="ada.admin@example.com",
        password="test-pass-123",
        role=User.Role.ADMIN,
        first_name="Ada",
        last_name="Admin",
        phone_number="+639170000000",
    )


@pytest.fixture
def rider(db):
    return User.objects.create_user(
        email="rita.rider@example.com",
        password="test-pass-123",
        role=User.Role.RIDER,
        first_name="Rita",
        last_name="Rider",
        phone_number="+639170000001",
    )


@pytest.fixture
def driver(db):
    return User.objects.create_user(
        email="chris.hernandez@example.com",
        password="test-pass-123",
        role=User.Role.DRIVER,
        first_name="Chris",
        last_name="Hernandez",
        phone_number="+639170000002",
    )


@pytest.fixture
def ride(db, rider, driver):
    return Ride.objects.create(
        status=Ride.Status.EN_ROUTE,
        id_rider=rider,
        id_driver=driver,
        pickup_latitude=14.5995,
        pickup_longitude=120.9842,
        dropoff_latitude=14.5547,
        dropoff_longitude=121.0244,
        pickup_time=timezone.now(),
    )


@pytest.fixture
def anonymous_api(db):
    """A client carrying no credentials at all."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def api(db, admin):
    """
    The client every endpoint test uses: signed in as an admin.

    Authentication lives in this one fixture so the endpoint tests stay about
    the endpoints rather than each re-stating how to log in.
    """
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=admin)
    return client
