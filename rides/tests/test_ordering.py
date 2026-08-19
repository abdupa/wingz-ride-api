"""Requirement 3: sort by pickup_time, with pagination still correct."""

from datetime import timedelta

import pytest
from django.utils import timezone

from rides.models import Ride


@pytest.mark.django_db
def test_sort_by_pickup_time_ascending(api, make_rides):
    base = timezone.now()
    for offset in (2, 0, 1):
        make_rides(1, pickup_time=base + timedelta(hours=offset))

    times = [r["pickup_time"] for r in api.get("/api/rides/?ordering=pickup_time").data["results"]]
    assert times == sorted(times)


@pytest.mark.django_db
def test_sort_by_pickup_time_descending(api, make_rides):
    base = timezone.now()
    for offset in (2, 0, 1):
        make_rides(1, pickup_time=base + timedelta(hours=offset))

    times = [r["pickup_time"] for r in api.get("/api/rides/?ordering=-pickup_time").data["results"]]
    assert times == sorted(times, reverse=True)


@pytest.mark.django_db
def test_ties_do_not_break_pagination(api, make_rides):
    """
    45 rides sharing one pickup_time -- the worst case for an unstable sort.

    Without a unique tiebreaker PostgreSQL may order the tied rows differently
    for each page, so a ride appears twice and another never appears. The count
    still reads 45, which is what makes it hard to spot.
    """
    make_rides(45, pickup_time=timezone.now())

    seen = []
    for page in (1, 2, 3):
        body = api.get(f"/api/rides/?ordering=pickup_time&page={page}").data
        seen += [r["id_ride"] for r in body["results"]]

    assert len(seen) == 45
    assert len(set(seen)) == 45


@pytest.mark.django_db
def test_the_primary_key_is_appended_to_every_ordering(api, make_rides):
    """Ties resolve by id_ride, so the order is total and reproducible."""
    make_rides(5, pickup_time=timezone.now())
    ids = [r["id_ride"] for r in api.get("/api/rides/?ordering=pickup_time").data["results"]]
    assert ids == sorted(ids)


@pytest.mark.django_db
def test_a_misspelled_ordering_field_is_400(api, make_rides):
    """
    DRF's default is to drop the term and return 200 with unsorted data, which
    hides the typo behind a response that looks correct.
    """
    make_rides(3)
    response = api.get("/api/rides/?ordering=pickup_tim")
    assert response.status_code == 400
    assert "ordering" in response.data


@pytest.mark.django_db
def test_ordering_is_limited_to_the_whitelist(api, make_rides):
    make_rides(3)
    assert api.get("/api/rides/?ordering=status").status_code == 400


@pytest.mark.django_db
def test_sorting_combines_with_filtering(api, make_rides):
    base = timezone.now()
    make_rides(2, status=Ride.Status.PICKUP, pickup_time=base)
    make_rides(3, status=Ride.Status.DROPOFF, pickup_time=base + timedelta(hours=1))

    body = api.get("/api/rides/?status=dropoff&ordering=-pickup_time").data
    assert body["count"] == 3
