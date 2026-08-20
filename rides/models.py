from django.db import models
from django.utils import timezone


class Ride(models.Model):
    """
    The assessment's Ride table.

    The spec states this table's structure cannot be changed, so there is no
    stored distance column and no created_at/updated_at audit fields, however
    conventional those would be. Indexes are added freely -- an index is not a
    structure change, and requirement 3 asks for both sorts to be as efficient
    as possible on a very large table.

    Every foreign key sets db_column explicitly. Django's default is to append
    "_id" to the field name, which would silently produce id_rider_id and
    id_driver_id instead of the columns the spec defines.
    """

    class Status(models.TextChoices):
        EN_ROUTE = "en-route", "En route"
        PICKUP = "pickup", "Pickup"
        DROPOFF = "dropoff", "Dropoff"

    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    # PROTECT, not CASCADE: deleting a user must not silently erase ride
    # history. The ViewSet turns the resulting ProtectedError into a 409.
    id_rider = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        db_column="id_rider",
        related_name="rides_as_rider",
    )
    id_driver = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        db_column="id_driver",
        related_name="rides_as_driver",
    )
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField()
    dropoff_longitude = models.FloatField()
    pickup_time = models.DateTimeField()

    class Meta:
        db_table = "ride"
        # Not decoration. PostgreSQL gives no guarantee about row order
        # without an ORDER BY, so an unordered queryset with LIMIT/OFFSET can
        # return the same row on two pages and skip another entirely.
        ordering = ["id_ride"]
        indexes = [
            # Composite, not pickup_time alone. Every ordering ends in the
            # primary key (see StrictOrderingFilter), so the query is really
            # ORDER BY pickup_time, id_ride. A single-column index leaves
            # PostgreSQL to sort the ties on top of the index scan; carrying
            # id_ride in the index makes the whole ordering readable straight
            # from it.
            models.Index(fields=["pickup_time", "id_ride"], name="ride_pickup_time_id_idx"),
            models.Index(fields=["status"], name="ride_status_idx"),
        ]
        # Coordinate bounds are physically true, so these can never reject
        # data the spec permits. A constraint that rider != driver was
        # considered and declined: the spec never states it, and rejecting
        # valid input looks like a bug.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pickup_latitude__gte=-90, pickup_latitude__lte=90),
                name="ride_pickup_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(pickup_longitude__gte=-180, pickup_longitude__lte=180),
                name="ride_pickup_longitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(dropoff_latitude__gte=-90, dropoff_latitude__lte=90),
                name="ride_dropoff_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(dropoff_longitude__gte=-180, dropoff_longitude__lte=180),
                name="ride_dropoff_longitude_range",
            ),
        ]

    def __str__(self):
        return f"Ride {self.id_ride} ({self.status})"


class RideEvent(models.Model):
    """
    The assessment's Ride_Event table, expected to grow very large.

    created_at uses default=timezone.now rather than auto_now_add. auto_now_add
    makes the field non-editable and always "now", which would make the bonus
    report impossible to seed with historical data, the 24-hour window in
    requirement 4 impossible to test at its boundary, and the create endpoint
    unable to accept a timestamp at all.
    """

    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        db_column="id_ride",
        related_name="events",
        # The composite index below already covers id_ride as its leftmost
        # column, so Django's automatic single-column FK index would be pure
        # duplicate write cost on a table this size.
        db_index=False,
    )
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ride_event"
        ordering = ["id_ride_event"]
        indexes = [
            # Serves two jobs: the 24-hour prefetch in requirement 4
            # (WHERE id_ride IN (...) AND created_at >= cutoff) and the
            # per-ride event lookup in the bonus report.
            models.Index(fields=["id_ride", "created_at"], name="ride_event_ride_time_idx"),
        ]

    def __str__(self):
        return f"RideEvent {self.id_ride_event}: {self.description}"
