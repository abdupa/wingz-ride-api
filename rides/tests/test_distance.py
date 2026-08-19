"""
Requirement 3: sort by distance to a given pickup GPS location.

The distance is computed in SQL. The tests check it against an independent
haversine written in Python, so a mistake in the ORM expression cannot be
confirmed by the same mistake in the assertion.
"""

import math

import pytest

from rides.distance import EARTH_RADIUS_KM

# Reference point: Rizal Park, Manila.
REF_LAT, REF_LNG = 14.5826, 120.9787

# Pickup points at increasing distance from it.
PLACES = {
    "intramuros": (14.5895, 120.9750),
    "makati": (14.5547, 121.0244),
    "quezon_city": (14.6760, 121.0437),
    "tagaytay": (14.1153, 120.9621),
}


def haversine_python(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@pytest.fixture
def places(make_rides):
    return {
        name: make_rides(1, pickup_latitude=lat, pickup_longitude=lng)[0]
        for name, (lat, lng) in PLACES.items()
    }


@pytest.mark.django_db
def test_the_database_agrees_with_an_independent_haversine(api, places):
    body = api.get(f"/api/rides/?lat={REF_LAT}&lng={REF_LNG}").data

    by_id = {ride.id_ride: name for name, ride in places.items()}
    for row in body["results"]:
        lat, lng = PLACES[by_id[row["id_ride"]]]
        expected = haversine_python(REF_LAT, REF_LNG, lat, lng)
        assert row["distance_km"] == pytest.approx(expected, abs=1e-6)


@pytest.mark.django_db
def test_sort_by_distance_nearest_first(api, places):
    body = api.get(f"/api/rides/?ordering=distance&lat={REF_LAT}&lng={REF_LNG}").data
    names = [n for n, r in sorted(places.items(), key=lambda kv: kv[1].id_ride)]  # noqa: F841
    distances = [row["distance_km"] for row in body["results"]]
    assert distances == sorted(distances)
    assert distances[0] < distances[-1]


@pytest.mark.django_db
def test_sort_by_distance_furthest_first(api, places):
    body = api.get(f"/api/rides/?ordering=-distance&lat={REF_LAT}&lng={REF_LNG}").data
    distances = [row["distance_km"] for row in body["results"]]
    assert distances == sorted(distances, reverse=True)


@pytest.mark.django_db
def test_sorting_happens_in_the_database_not_on_the_page(api, make_rides):
    """
    45 rides, 20 to a page. If the sort ran in Python after fetching, page 1
    would hold the 20 lowest ids sorted among themselves -- not the 20 nearest
    rides overall. The nearest ride is created last, so it would be missing.
    """
    for i in range(44):
        make_rides(1, pickup_latitude=REF_LAT + 1 + (i * 0.01), pickup_longitude=REF_LNG)
    nearest = make_rides(1, pickup_latitude=REF_LAT, pickup_longitude=REF_LNG)[0]

    body = api.get(
        f"/api/rides/?ordering=distance&lat={REF_LAT}&lng={REF_LNG}&page=1"
    ).data
    assert body["results"][0]["id_ride"] == nearest.id_ride


@pytest.mark.django_db
def test_pagination_holds_when_sorting_by_distance(api, make_rides):
    for i in range(45):
        make_rides(1, pickup_latitude=REF_LAT + (i * 0.01), pickup_longitude=REF_LNG)

    seen = []
    for page in (1, 2, 3):
        body = api.get(
            f"/api/rides/?ordering=distance&lat={REF_LAT}&lng={REF_LNG}&page={page}"
        ).data
        seen += [row["id_ride"] for row in body["results"]]

    assert len(seen) == 45
    assert len(set(seen)) == 45


@pytest.mark.django_db
def test_identical_pickups_still_paginate_cleanly(api, make_rides):
    """Every ride at the same point -- the worst case for a tie."""
    make_rides(45, pickup_latitude=REF_LAT, pickup_longitude=REF_LNG)

    seen = []
    for page in (1, 2, 3):
        body = api.get(
            f"/api/rides/?ordering=distance&lat={REF_LAT}&lng={REF_LNG}&page={page}"
        ).data
        seen += [row["id_ride"] for row in body["results"]]

    assert len(set(seen)) == 45


@pytest.mark.django_db
def test_distance_is_absent_when_no_reference_point_is_given(api, ride):
    body = api.get("/api/rides/").data
    assert "distance_km" not in body["results"][0]


@pytest.mark.django_db
def test_distance_combines_with_filtering(api, make_rides, rider):
    from rides.models import Ride

    make_rides(3, status=Ride.Status.PICKUP, pickup_latitude=REF_LAT, pickup_longitude=REF_LNG)
    make_rides(2, status=Ride.Status.DROPOFF, pickup_latitude=REF_LAT, pickup_longitude=REF_LNG)
    body = api.get(
        f"/api/rides/?status=pickup&ordering=distance&lat={REF_LAT}&lng={REF_LNG}"
    ).data
    assert body["count"] == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query,missing",
    [
        ("ordering=distance", "lat"),
        (f"ordering=distance&lat={REF_LAT}", "lng"),
        (f"ordering=distance&lng={REF_LNG}", "lat"),
    ],
)
def test_sorting_by_distance_without_a_point_is_400(api, ride, query, missing):
    response = api.get(f"/api/rides/?{query}")
    assert response.status_code == 400
    assert missing in response.data


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lat,lng",
    [(91, 120), (-91, 120), (14, 181), (14, -181), ("north", 120), (14, "east")],
)
def test_impossible_reference_points_are_400(api, ride, lat, lng):
    response = api.get(f"/api/rides/?ordering=distance&lat={lat}&lng={lng}")
    assert response.status_code == 400


@pytest.mark.django_db
def test_the_query_budget_survives_distance_sorting(
    api, make_rides, django_assert_num_queries
):
    """An annotation adds an expression to the SELECT, never another query."""
    make_rides(30, pickup_latitude=REF_LAT, pickup_longitude=REF_LNG)
    with django_assert_num_queries(3):
        api.get(f"/api/rides/?ordering=distance&lat={REF_LAT}&lng={REF_LNG}")
