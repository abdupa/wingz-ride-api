"""Requirement 3: pagination, filter by status, filter by rider email."""

import pytest

from rides.models import Ride
from users.models import User


@pytest.mark.django_db
def test_list_is_paginated(api, make_rides):
    make_rides(25)
    body = api.get("/api/rides/").data
    assert body["count"] == 25
    assert len(body["results"]) == 20
    assert body["next"] is not None
    assert body["previous"] is None


@pytest.mark.django_db
def test_page_size_can_be_set_and_is_capped(api, make_rides):
    make_rides(30)
    assert len(api.get("/api/rides/?page_size=5").data["results"]) == 5
    # Above max_page_size the ceiling applies rather than the request.
    assert len(api.get("/api/rides/?page_size=1000").data["results"]) == 30


@pytest.mark.django_db
def test_a_row_never_appears_on_two_pages(api, make_rides):
    """
    Without a deterministic ordering, PostgreSQL is free to return rows in a
    different order for each page -- so a ride can appear twice while another
    is never returned at all. Meta.ordering is what prevents it.
    """
    make_rides(45)
    seen = []
    for page in (1, 2, 3):
        seen += [r["id_ride"] for r in api.get(f"/api/rides/?page={page}").data["results"]]
    assert len(seen) == 45
    assert len(set(seen)) == 45


@pytest.mark.django_db
def test_page_past_the_end_is_404(api, make_rides):
    make_rides(5)
    assert api.get("/api/rides/?page=99").status_code == 404


@pytest.mark.django_db
def test_filter_by_status(api, make_rides):
    make_rides(3, status=Ride.Status.EN_ROUTE)
    make_rides(2, status=Ride.Status.DROPOFF)
    assert api.get("/api/rides/?status=dropoff").data["count"] == 2
    assert api.get("/api/rides/?status=en-route").data["count"] == 3


@pytest.mark.django_db
def test_unknown_status_is_400_not_an_empty_list(api, make_rides):
    """An empty list would read as 'no rides matched', hiding the typo."""
    make_rides(3)
    response = api.get("/api/rides/?status=teleported")
    assert response.status_code == 400
    assert "status" in response.data


@pytest.mark.django_db
def test_filter_by_rider_email(api, make_rides, rider, driver):
    make_rides(4)
    other = User.objects.create_user(
        email="someone.else@example.com",
        password="test-pass-123",
        role=User.Role.RIDER,
        first_name="Other",
        last_name="Rider",
        phone_number="+639170000099",
    )
    Ride.objects.filter(pk__in=[r.pk for r in Ride.objects.all()[:1]]).update(id_rider=other)

    assert api.get(f"/api/rides/?rider_email={rider.email}").data["count"] == 3
    assert api.get(f"/api/rides/?rider_email={other.email}").data["count"] == 1


@pytest.mark.django_db
def test_rider_email_filter_ignores_case(api, make_rides, rider):
    """Emails are canonical lowercase in storage, so the caller's case is theirs."""
    make_rides(2)
    assert api.get(f"/api/rides/?rider_email={rider.email.upper()}").data["count"] == 2


@pytest.mark.django_db
def test_unknown_rider_email_returns_an_empty_page(api, make_rides):
    make_rides(3)
    body = api.get("/api/rides/?rider_email=nobody@example.com").data
    assert body["count"] == 0
    assert body["results"] == []


@pytest.mark.django_db
def test_filters_combine(api, make_rides, rider):
    make_rides(3, status=Ride.Status.EN_ROUTE)
    make_rides(2, status=Ride.Status.PICKUP)
    body = api.get(f"/api/rides/?status=pickup&rider_email={rider.email}").data
    assert body["count"] == 2
