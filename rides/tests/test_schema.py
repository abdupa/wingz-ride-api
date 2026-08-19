"""
Schema tests.

These assert what PostgreSQL actually built, not what the models declare.
Django appends "_id" to foreign key columns by default, so a model that reads
correctly can still produce id_rider_id in the database -- with no error and
no warning. Only the database can settle it.
"""

import pytest
from django.db import connection, transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from rides.models import Ride, RideEvent

# Column names and order exactly as the assessment's table definitions give them.
SPEC_COLUMNS = {
    "ride": [
        "id_ride",
        "status",
        "id_rider",
        "id_driver",
        "pickup_latitude",
        "pickup_longitude",
        "dropoff_latitude",
        "dropoff_longitude",
        "pickup_time",
    ],
    "ride_event": [
        "id_ride_event",
        "id_ride",
        "description",
        "created_at",
    ],
}


def actual_columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = %s "
            "order by ordinal_position",
            [table],
        )
        return [row[0] for row in cursor.fetchall()]


@pytest.mark.django_db
@pytest.mark.parametrize("table,expected", SPEC_COLUMNS.items())
def test_table_matches_the_spec(table, expected):
    assert actual_columns(table) == expected


@pytest.mark.django_db
def test_created_at_accepts_a_historical_timestamp(ride):
    """
    Guards against auto_now_add, which would overwrite this silently.

    The bonus report groups trips by month across a range of months, and the
    24-hour window needs events either side of the boundary. Neither is
    possible if the database stamps every row with the current time.
    """
    backdated = timezone.now() - timezone.timedelta(days=200)
    event = RideEvent.objects.create(
        id_ride=ride,
        description="Status changed to pickup",
        created_at=backdated,
    )
    event.refresh_from_db()
    assert event.created_at == backdated


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("pickup_latitude", 91.0),
        ("pickup_longitude", 181.0),
        ("dropoff_latitude", -91.0),
        ("dropoff_longitude", -181.0),
    ],
)
def test_coordinates_outside_earth_are_rejected(ride, field, bad_value):
    setattr(ride, field, bad_value)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ride.save()


@pytest.mark.django_db
def test_deleting_a_user_with_rides_is_blocked(ride, rider):
    """Ride history must survive a user deletion, so the FK is PROTECT."""
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        rider.delete()


@pytest.mark.django_db
def test_deleting_a_ride_removes_its_events(ride):
    """An event has no meaning without its ride, so that FK cascades."""
    RideEvent.objects.create(id_ride=ride, description="Status changed to pickup")
    ride.delete()
    assert RideEvent.objects.count() == 0
