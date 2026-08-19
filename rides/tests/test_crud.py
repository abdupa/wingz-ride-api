import pytest
from django.utils import timezone

from rides.models import Ride, RideEvent

SPEC_RIDE_FIELDS = [
    "id_ride",
    "status",
    "id_rider",
    "id_driver",
    "pickup_latitude",
    "pickup_longitude",
    "dropoff_latitude",
    "dropoff_longitude",
    "pickup_time",
]


def ride_payload(rider, driver, **overrides):
    payload = {
        "status": "en-route",
        "id_rider": rider.id_user,
        "id_driver": driver.id_user,
        "pickup_latitude": 14.5995,
        "pickup_longitude": 120.9842,
        "dropoff_latitude": 14.5547,
        "dropoff_longitude": 121.0244,
        "pickup_time": timezone.now().isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_ride_takes_plain_ids(api, rider, driver):
    response = api.post("/api/rides/", ride_payload(rider, driver), format="json")
    assert response.status_code == 201
    assert Ride.objects.get(pk=response.data["id_ride"]).id_rider == rider


@pytest.mark.django_db
def test_read_nests_rider_and_driver(api, ride):
    response = api.get(f"/api/rides/{ride.id_ride}/")
    assert response.status_code == 200
    assert response.data["id_rider"]["email"] == ride.id_rider.email
    assert response.data["id_driver"]["first_name"] == ride.id_driver.first_name


@pytest.mark.django_db
def test_ride_fields_are_in_the_order_the_spec_lists_them(api, ride):
    """The spec's nine fields come first, in its order; extras follow."""
    keys = list(api.get(f"/api/rides/{ride.id_ride}/").data.keys())
    assert keys[: len(SPEC_RIDE_FIELDS)] == SPEC_RIDE_FIELDS
    assert keys[len(SPEC_RIDE_FIELDS) :] == ["todays_ride_events", "ride_events_url"]


@pytest.mark.django_db
def test_update_and_delete_ride(api, ride):
    assert api.patch(
        f"/api/rides/{ride.id_ride}/", {"status": "pickup"}, format="json"
    ).status_code == 200
    ride.refresh_from_db()
    assert ride.status == "pickup"
    assert api.delete(f"/api/rides/{ride.id_ride}/").status_code == 204


@pytest.mark.django_db
def test_impossible_coordinates_are_a_400_not_a_500(api, rider, driver):
    response = api.post(
        "/api/rides/", ride_payload(rider, driver, pickup_latitude=91.0), format="json"
    )
    assert response.status_code == 400
    assert "pickup_latitude" in response.data


@pytest.mark.django_db
def test_ride_event_crud(api, ride):
    created = api.post(
        "/api/ride-events/",
        {"id_ride": ride.id_ride, "description": "Status changed to pickup"},
        format="json",
    )
    assert created.status_code == 201
    assert list(created.data.keys()) == [
        "id_ride_event",
        "id_ride",
        "description",
        "created_at",
    ]

    pk = created.data["id_ride_event"]
    assert api.get(f"/api/ride-events/{pk}/").status_code == 200
    assert api.patch(
        f"/api/ride-events/{pk}/", {"description": "Status changed to dropoff"}, format="json"
    ).status_code == 200
    assert api.delete(f"/api/ride-events/{pk}/").status_code == 204
    assert RideEvent.objects.count() == 0
