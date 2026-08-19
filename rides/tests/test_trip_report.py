"""
Bonus: trips over one hour, by month and driver.

The interesting test is test_the_naive_double_join_inflates_and_ours_does_not.
The rest pin the details the brief's sample output specifies.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from rides.management.commands.trip_report import run_report
from rides.models import Ride, RideEvent
from users.models import User

PICKUP = "Status changed to pickup"
DROPOFF = "Status changed to dropoff"

NAIVE_QUERY = """
    SELECT to_char(p.created_at, 'YYYY-MM'),
           d.first_name || ' ' || LEFT(d.last_name, 1),
           COUNT(*)
    FROM ride r
    JOIN ride_event p  ON p.id_ride  = r.id_ride AND p.description = 'Status changed to pickup'
    JOIN ride_event dr ON dr.id_ride = r.id_ride AND dr.description = 'Status changed to dropoff'
    JOIN "user" d ON d.id_user = r.id_driver
    WHERE dr.created_at - p.created_at > INTERVAL '1 hour'
    GROUP BY 1, 2
    ORDER BY 1, 2;
"""


@pytest.fixture
def trip(rider, driver):
    """Builds one ride and returns a helper to attach events to it."""

    def _trip(minutes, when=None, extra_pickups=0, dropoff=True, drv=None):
        started = when or timezone.now() - timedelta(days=10)
        ride = Ride.objects.create(
            status=Ride.Status.DROPOFF,
            id_rider=rider,
            id_driver=drv or driver,
            pickup_latitude=14.5, pickup_longitude=120.9,
            dropoff_latitude=14.6, dropoff_longitude=121.0,
            pickup_time=started,
        )
        RideEvent.objects.create(id_ride=ride, description=PICKUP, created_at=started)
        for i in range(extra_pickups):
            RideEvent.objects.create(
                id_ride=ride, description=PICKUP,
                created_at=started + timedelta(minutes=i + 1),
            )
        if dropoff:
            RideEvent.objects.create(
                id_ride=ride, description=DROPOFF,
                created_at=started + timedelta(minutes=minutes),
            )
        return ride

    return _trip


def naive_report():
    with connection.cursor() as cursor:
        cursor.execute(NAIVE_QUERY)
        return cursor.fetchall()


# --- the one that matters ---------------------------------------------------


@pytest.mark.django_db
def test_the_naive_double_join_inflates_and_ours_does_not(trip):
    """
    One ride, 90 minutes, with a second pickup event recorded a minute in.

    Joining ride_event twice matches both pickups against the dropoff and
    counts the trip twice. Nothing errors -- the number is simply too high and
    looks completely reasonable. Collapsing the events per ride first gives 1.
    """
    trip(minutes=90, extra_pickups=1)

    assert naive_report()[0][2] == 2      # wrong, and plausible
    assert run_report()[0][2] == 1        # right


# --- the boundary -----------------------------------------------------------


@pytest.mark.django_db
def test_exactly_one_hour_does_not_count(trip):
    """The brief says more than one hour, so 60 minutes is out."""
    trip(minutes=60)
    assert run_report() == []


@pytest.mark.django_db
def test_one_minute_over_counts(trip):
    trip(minutes=61)
    assert run_report()[0][2] == 1


# --- shape of the output ----------------------------------------------------


@pytest.mark.django_db
def test_the_driver_is_first_name_plus_last_initial(trip, driver):
    trip(minutes=90)
    assert run_report()[0][1] == f"{driver.first_name} {driver.last_name[0]}"


@pytest.mark.django_db
def test_the_month_is_the_pickup_month(trip):
    when = timezone.now() - timedelta(days=40)
    trip(minutes=90, when=when)
    assert run_report()[0][0] == when.strftime("%Y-%m")


@pytest.mark.django_db
def test_rows_are_grouped_by_month_and_driver(trip):
    january = timezone.now() - timedelta(days=70)
    february = timezone.now() - timedelta(days=40)
    trip(minutes=90, when=january)
    trip(minutes=90, when=january + timedelta(days=1))
    trip(minutes=120, when=february)

    rows = run_report()
    assert len(rows) == 2
    assert [row[2] for row in rows] == [2, 1]


# --- what must be excluded --------------------------------------------------


@pytest.mark.django_db
def test_a_trip_still_running_is_excluded(trip):
    trip(minutes=90, dropoff=False)
    assert run_report() == []


@pytest.mark.django_db
def test_a_short_trip_is_excluded(trip):
    trip(minutes=90)
    trip(minutes=20)
    assert run_report()[0][2] == 1


# --- the collision the brief's format invites -------------------------------


@pytest.mark.django_db
def test_two_drivers_with_the_same_initial_stay_separate(trip, driver):
    """
    Chris Hernandez and Chris Huang both render as "Chris H". Grouping by the
    displayed name would silently merge them into a single row.
    """
    other = User.objects.create_user(
        email="chris.huang@example.com",
        password="test-pass-123",
        role=User.Role.DRIVER,
        first_name="Chris",
        last_name="Huang",
        phone_number="+639170000055",
    )
    when = timezone.now() - timedelta(days=10)
    trip(minutes=90, when=when)
    trip(minutes=90, when=when, drv=other)

    rows = run_report()
    assert len(rows) == 2
    assert [row[1] for row in rows] == ["Chris H", "Chris H"]
    assert [row[2] for row in rows] == [1, 1]


# --- the brief's own sample report ------------------------------------------

# Reproduced verbatim from the assessment PDF.
SAMPLE_REPORT = [
    ("2024-01", "Chris H", 4),
    ("2024-01", "Howard Y", 5),
    ("2024-01", "Randy W", 2),
    ("2024-02", "Chris H", 7),
    ("2024-02", "Howard Y", 5),
    ("2024-03", "Chris H", 2),
    ("2024-03", "Howard Y", 2),
    ("2024-03", "Randy W", 11),
    ("2024-04", "Howard Y", 7),
    ("2024-04", "Randy W", 3),
]

SAMPLE_DRIVERS = {
    "Chris H": ("Chris", "Hernandez"),
    "Howard Y": ("Howard", "Yamamoto"),
    "Randy W": ("Randy", "Watanabe"),
}


@pytest.fixture
def sample_drivers(db):
    return {
        label: User.objects.create_user(
            email=f"{first}.{last}@example.com".lower(),
            password="test-pass-123",
            role=User.Role.DRIVER,
            first_name=first,
            last_name=last,
            phone_number="+639170000000",
        )
        for label, (first, last) in SAMPLE_DRIVERS.items()
    }


def build_trips(rider, driver, month, count, minutes):
    """`count` trips of `minutes` each, mid-month so no boundary is involved."""
    from datetime import datetime, timezone as dt_timezone

    year, mon = (int(part) for part in month.split("-"))
    start = datetime(year, mon, 15, 12, 0, tzinfo=dt_timezone.utc)

    rides = Ride.objects.bulk_create(
        [
            Ride(
                status=Ride.Status.DROPOFF,
                id_rider=rider,
                id_driver=driver,
                pickup_latitude=14.5, pickup_longitude=120.9,
                dropoff_latitude=14.6, dropoff_longitude=121.0,
                pickup_time=start + timedelta(minutes=i),
            )
            for i in range(count)
        ]
    )
    RideEvent.objects.bulk_create(
        [
            event
            for i, ride in enumerate(rides)
            for event in (
                RideEvent(id_ride=ride, description=PICKUP,
                          created_at=start + timedelta(minutes=i)),
                RideEvent(id_ride=ride, description=DROPOFF,
                          created_at=start + timedelta(minutes=i + minutes)),
            )
        ]
    )


@pytest.mark.django_db
def test_it_reproduces_the_briefs_sample_report(rider, sample_drivers):
    """
    Builds exactly the dataset the assessment's sample report describes, then
    asserts the query returns exactly that table -- same months, same driver
    labels, same counts, same order.

    Noise is added on purpose in the two cells the sample leaves blank. The
    brief shows no Randy W in February and no Chris H in April, so those
    drivers get short trips in those months. If the query were counting all
    trips rather than only those over an hour, two extra rows would appear and
    the comparison would fail.
    """
    for month, label, count in SAMPLE_REPORT:
        build_trips(rider, sample_drivers[label], month, count, minutes=90)

    # The blanks in the sample, populated with trips that must not qualify.
    build_trips(rider, sample_drivers["Randy W"], "2024-02", 6, minutes=45)
    build_trips(rider, sample_drivers["Chris H"], "2024-04", 9, minutes=59)
    # And one that is exactly an hour, which "more than 1 hour" excludes.
    build_trips(rider, sample_drivers["Howard Y"], "2024-02", 3, minutes=60)

    assert run_report() == SAMPLE_REPORT
