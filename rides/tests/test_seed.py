"""
The seed command exists to make the rest provable: the bonus report needs
months of pickup and dropoff events, and several tests need shapes that
uniform random data would never produce.

These tests assert those shapes are actually there, because a seed that
silently stopped producing them would make the report look correct while
testing nothing.
"""

import pytest
from django.core.management import call_command
from django.db.models import Count, Q
from django.utils import timezone

from rides.management.commands.seed import ADMIN_EMAIL, DROPOFF, PICKUP
from rides.models import Ride, RideEvent
from users.models import User


@pytest.fixture
def seeded(db):
    call_command("seed", rides=60, verbosity=0)


@pytest.mark.django_db
def test_it_creates_an_admin_that_can_log_in(seeded):
    admin = User.objects.get(email=ADMIN_EMAIL)
    assert admin.is_admin
    assert admin.check_password("wingz-admin-password")


@pytest.mark.django_db
def test_every_email_is_stored_lowercase(seeded):
    """bulk_create bypasses save(), so this is the path that used to break."""
    assert not User.objects.exclude(email=None).filter(email__regex=r"[A-Z]").exists()


@pytest.mark.django_db
def test_it_is_deterministic(db):
    call_command("seed", rides=25, seed=7, clear=True, verbosity=0)
    first = list(Ride.objects.order_by("id_ride").values_list("pickup_latitude", flat=True))

    call_command("seed", rides=25, seed=7, clear=True, verbosity=0)
    second = list(Ride.objects.order_by("id_ride").values_list("pickup_latitude", flat=True))

    assert first == second


@pytest.mark.django_db
def test_it_creates_a_ride_straddling_the_24_hour_boundary(seeded):
    """One event inside the window, one outside, on the same ride."""
    cutoff = timezone.now() - timezone.timedelta(hours=24)
    straddling = (
        Ride.objects.annotate(
            inside=Count("events", filter=Q(events__created_at__gte=cutoff)),
            outside=Count("events", filter=Q(events__created_at__lt=cutoff)),
        )
        .filter(inside__gt=0, outside__gt=0)
    )
    assert straddling.exists()


@pytest.mark.django_db
def test_it_creates_rides_sharing_one_pickup_time(seeded):
    """Ordering ties are only testable if ties exist."""
    tied = (
        Ride.objects.values("pickup_time")
        .annotate(n=Count("id_ride"))
        .filter(n__gte=5)
    )
    assert tied.exists()


@pytest.mark.django_db
def test_it_creates_a_ride_with_two_pickup_events(seeded):
    """
    The bonus report's inflation bug is invisible without this row: joining
    ride_event twice counts such a trip once per pickup, and with one pickup
    per ride the wrong query and the right one agree.
    """
    doubled = (
        Ride.objects.annotate(pickups=Count("events", filter=Q(events__description=PICKUP)))
        .filter(pickups__gte=2)
    )
    assert doubled.exists()


@pytest.mark.django_db
def test_it_creates_trips_on_both_sides_of_one_hour(seeded):
    """The report counts trips over an hour, so it needs some under it too."""
    durations = []
    for ride in Ride.objects.prefetch_related("events"):
        pickups = [e.created_at for e in ride.events.all() if e.description == PICKUP]
        dropoffs = [e.created_at for e in ride.events.all() if e.description == DROPOFF]
        if pickups and dropoffs:
            durations.append((max(dropoffs) - min(pickups)).total_seconds() / 3600)

    assert any(d > 1 for d in durations)
    assert any(0 < d <= 1 for d in durations)


@pytest.mark.django_db
def test_events_span_several_months(seeded):
    oldest = RideEvent.objects.order_by("created_at").first().created_at
    assert (timezone.now() - oldest).days > 60


@pytest.mark.django_db
def test_clear_empties_previous_data(db):
    call_command("seed", rides=10, verbosity=0)
    before = Ride.objects.count()
    call_command("seed", rides=10, clear=True, verbosity=0)
    assert Ride.objects.count() < before * 2
