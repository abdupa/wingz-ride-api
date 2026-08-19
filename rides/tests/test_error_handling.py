"""
Error handling is one of the four evaluation criteria, so it gets its own
suite rather than being assumed.

Every case below was found by walking the API's edge cases and recording what
it actually returned. One of them was a 500; the rest already behaved, and are
pinned here so they stay that way.
"""

import pytest
from django.utils import timezone

from rides.models import Ride


@pytest.fixture
def tolerant_api(admin):
    """A client that reports server errors rather than re-raising them."""
    from rest_framework.test import APIClient

    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user=admin)
    return client


# --- the one that was a 500 -------------------------------------------------


@pytest.mark.django_db
def test_deleting_a_user_with_rides_is_409_not_500(tolerant_api, ride, rider):
    """
    PROTECT on the rider foreign key means ride history survives a user
    deletion. Django raises ProtectedError, which DRF does not know about, so
    before the custom handler this was an unhandled 500.
    """
    response = tolerant_api.delete(f"/api/users/{rider.id_user}/")
    assert response.status_code == 409
    assert "cannot be deleted" in response.data["detail"]


@pytest.mark.django_db
def test_the_user_still_exists_after_a_refused_delete(tolerant_api, ride, rider):
    from users.models import User

    tolerant_api.delete(f"/api/users/{rider.id_user}/")
    assert User.objects.filter(pk=rider.pk).exists()


@pytest.mark.django_db
def test_a_user_with_no_rides_deletes_normally(tolerant_api, rider):
    """The guard must not block legitimate deletions."""
    assert tolerant_api.delete(f"/api/users/{rider.id_user}/").status_code == 204


# --- silently-ignored parameters --------------------------------------------


@pytest.mark.django_db
def test_an_unparseable_page_size_is_400(api, make_rides):
    """
    DRF's default is to discard it and serve the default page size with a 200,
    so the caller never learns their parameter was thrown away.
    """
    make_rides(3)
    response = api.get("/api/rides/?page_size=abc")
    assert response.status_code == 400
    assert "page_size" in response.data


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_nonsensical_page_size_is_400(api, make_rides, value):
    make_rides(3)
    assert api.get(f"/api/rides/?page_size={value}").status_code == 400


# --- malformed requests -----------------------------------------------------


@pytest.mark.django_db
def test_malformed_json_is_400(api):
    response = api.post("/api/rides/", data="{not json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_an_unsupported_content_type_is_415(api):
    assert api.post("/api/rides/", data="a=1", content_type="text/plain").status_code == 415


@pytest.mark.django_db
def test_an_unsupported_method_is_405(api):
    assert api.put("/api/rides/", {}, format="json").status_code == 405


@pytest.mark.django_db
def test_a_missing_object_is_404(api):
    assert api.get("/api/rides/999999/").status_code == 404


@pytest.mark.django_db
def test_a_page_past_the_end_is_404(api, make_rides):
    make_rides(3)
    assert api.get("/api/rides/?page=99").status_code == 404


# --- references that do not exist -------------------------------------------


@pytest.mark.django_db
def test_creating_a_ride_for_a_missing_user_is_400(api):
    response = api.post(
        "/api/rides/",
        {
            "status": "en-route",
            "id_rider": 999999,
            "id_driver": 999999,
            "pickup_latitude": 14.5,
            "pickup_longitude": 120.9,
            "dropoff_latitude": 14.6,
            "dropoff_longitude": 121.0,
            "pickup_time": timezone.now().isoformat(),
        },
        format="json",
    )
    assert response.status_code == 400
    assert "id_rider" in response.data


@pytest.mark.django_db
def test_creating_an_event_for_a_missing_ride_is_400(api):
    response = api.post(
        "/api/ride-events/", {"id_ride": 999999, "description": "x"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_duplicate_email_is_400(api, admin):
    response = api.post(
        "/api/users/",
        {
            "role": "rider",
            "first_name": "Copy",
            "last_name": "Cat",
            "email": admin.email,
            "phone_number": "+639170000077",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "email" in response.data


@pytest.mark.django_db
def test_missing_required_fields_are_400(api):
    response = api.post("/api/rides/", {}, format="json")
    assert response.status_code == 400
    assert "status" in response.data


@pytest.mark.django_db
def test_a_non_numeric_filter_value_is_400(api, ride):
    assert api.get("/api/ride-events/?id_ride=abc").status_code == 400


# --- nothing anywhere should be a 5xx ---------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/rides/?page=abc",
        "/api/rides/?page_size=abc",
        "/api/rides/?status=teleported",
        "/api/rides/?ordering=nonsense",
        "/api/rides/?ordering=distance",
        "/api/rides/?ordering=distance&lat=abc&lng=1",
        "/api/rides/?lat=999&lng=999",
        "/api/rides/?rider_email=not-an-email",
        "/api/ride-events/?id_ride=abc",
        "/api/rides/999999/",
    ],
)
def test_no_edge_case_returns_a_server_error(tolerant_api, ride, path):
    assert tolerant_api.get(path).status_code < 500
