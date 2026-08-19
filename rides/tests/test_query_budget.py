"""
Requirement 4: todays_ride_events, and the query budget.

This is the only requirement in the brief with a number attached, so it is the
only one that can be measured rather than judged. These tests are the proof.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from rides.models import Ride, RideEvent


def add_events(rides, hours_ago):
    RideEvent.objects.bulk_create(
        [
            RideEvent(
                id_ride=ride,
                description="Status changed to pickup",
                created_at=timezone.now() - timedelta(hours=hours_ago),
            )
            for ride in rides
        ]
    )


@pytest.mark.django_db
@pytest.mark.parametrize("n_rides", [5, 50])
def test_the_query_count_does_not_grow_with_the_data(
    api, make_rides, django_assert_num_queries, n_rides
):
    """
    Three queries at one data size is an observation. Three at two sizes, ten
    times apart, is evidence the cost is constant.

    The page holds 20 rides, so a per-row query would show as 23 here, not 3.

    Three is the brief's number: one for the rides with their rider and driver
    joined, one for the events, one for the paginator's COUNT. Authentication
    is not part of what the brief measures -- force_authenticate is used, so
    this counts fetching the list and nothing else. Over the wire a real token
    adds one lookup; see the README.
    """
    rides = make_rides(n_rides)
    add_events(rides, hours_ago=1)

    with django_assert_num_queries(3):
        response = api.get("/api/rides/")
    assert response.status_code == 200
    assert response.data["count"] == n_rides


@pytest.mark.django_db
def test_a_single_ride_also_costs_no_per_row_query(
    api, ride, django_assert_num_queries
):
    add_events([ride], hours_ago=1)
    with django_assert_num_queries(2):  # no COUNT on a detail route
        api.get(f"/api/rides/{ride.id_ride}/")


@pytest.mark.django_db
def test_only_the_last_24_hours_are_returned(api, ride):
    recent = RideEvent.objects.create(
        id_ride=ride,
        description="Status changed to pickup",
        created_at=timezone.now() - timedelta(hours=23),
    )
    RideEvent.objects.create(
        id_ride=ride,
        description="Status changed to dropoff",
        created_at=timezone.now() - timedelta(hours=25),
    )

    body = api.get(f"/api/rides/{ride.id_ride}/").data
    returned = [event["id_ride_event"] for event in body["todays_ride_events"]]
    assert returned == [recent.id_ride_event]


@pytest.mark.django_db
def test_the_window_is_24_hours_not_today(api, ride):
    """
    The field is named todays_ride_events but the brief defines it as "the
    RideEvents from the last 24 hours". Those differ: at 09:00 a calendar day
    reaches back nine hours, a rolling window reaches into yesterday afternoon.
    An event from 20 hours ago belongs to yesterday and must still be returned.
    """
    event = RideEvent.objects.create(
        id_ride=ride,
        description="Status changed to pickup",
        created_at=timezone.now() - timedelta(hours=20),
    )
    body = api.get(f"/api/rides/{ride.id_ride}/").data
    assert [e["id_ride_event"] for e in body["todays_ride_events"]] == [event.id_ride_event]


@pytest.mark.django_db
def test_a_ride_with_no_recent_events_returns_an_empty_list(api, ride):
    RideEvent.objects.create(
        id_ride=ride,
        description="Status changed to pickup",
        created_at=timezone.now() - timedelta(days=3),
    )
    assert api.get(f"/api/rides/{ride.id_ride}/").data["todays_ride_events"] == []


@pytest.mark.django_db
def test_events_are_newest_first(api, ride):
    older = RideEvent.objects.create(
        id_ride=ride, description="Status changed to pickup",
        created_at=timezone.now() - timedelta(hours=5),
    )
    newer = RideEvent.objects.create(
        id_ride=ride, description="Status changed to dropoff",
        created_at=timezone.now() - timedelta(hours=1),
    )
    body = api.get(f"/api/rides/{ride.id_ride}/").data
    assert [e["id_ride_event"] for e in body["todays_ride_events"]] == [
        newer.id_ride_event,
        older.id_ride_event,
    ]


@pytest.mark.django_db
def test_events_belong_to_their_own_ride(api, make_rides):
    """A prefetch that leaks across rows would still return the right count."""
    first, second = make_rides(2)
    mine = RideEvent.objects.create(id_ride=first, description="mine")
    RideEvent.objects.create(id_ride=second, description="theirs")

    results = {r["id_ride"]: r for r in api.get("/api/rides/").data["results"]}
    assert [e["id_ride_event"] for e in results[first.id_ride]["todays_ride_events"]] == [
        mine.id_ride_event
    ]


@pytest.mark.django_db
def test_full_history_is_linked_rather_than_inlined(api, ride):
    """
    Requirement 3 wants the related RideEvents; requirement 4 forbids loading
    them all. The link resolves both, and costs no query.
    """
    RideEvent.objects.create(
        id_ride=ride, description="ancient",
        created_at=timezone.now() - timedelta(days=90),
    )
    url = api.get(f"/api/rides/{ride.id_ride}/").data["ride_events_url"]
    # Absolute, matching the paginator's next/previous links.
    assert url.startswith("http://")
    assert url.endswith(f"/api/ride-events/?id_ride={ride.id_ride}")
    assert api.get(url).data["count"] == 1
