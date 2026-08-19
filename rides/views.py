from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import viewsets

from .filters import RideFilter
from .models import Ride, RideEvent
from .serializers import RideEventSerializer, RideReadSerializer, RideWriteSerializer

TODAYS_EVENTS_WINDOW = timedelta(hours=24)


class RideViewSet(viewsets.ModelViewSet):
    """
    Full CRUD over the assessment's Ride table.

    Query optimisation lives here rather than in the serializers, so the cost
    of a request is readable in one place and the serializers stay thin.
    """

    queryset = Ride.objects.all()
    filterset_class = RideFilter
    ordering_fields = ["pickup_time"]

    def get_queryset(self):
        queryset = Ride.objects.all()
        if self.action not in ("list", "retrieve"):
            # Writes fetch a single row and serialise it back with plain ids.
            # The joins and the prefetch would be paid for and thrown away.
            return queryset

        # Computed per request. As a module constant or class attribute this
        # would freeze at server start, and the window would silently drift --
        # correct on the day of deploy, hours stale a week later, never an error.
        cutoff = timezone.now() - TODAYS_EVENTS_WINDOW

        return queryset.select_related(
            # Two joins onto the user table, aliased by Django. One query, not
            # one per ride.
            "id_rider",
            "id_driver",
        ).prefetch_related(
            # to_attr is what makes this safe. It puts a plain list on each
            # Ride, so the serializer reads an attribute and has no queryset to
            # accidentally re-filter. Without it, calling .filter() on the
            # prefetched relation discards the cache and re-queries per row --
            # paying for the prefetch and the N+1 both.
            Prefetch(
                "events",
                queryset=RideEvent.objects.filter(created_at__gte=cutoff).order_by(
                    "-created_at"
                ),
                to_attr="todays_ride_events",
            )
        )

    def get_serializer_class(self):
        # Reads nest rider and driver; writes take plain ids.
        if self.action in ("list", "retrieve"):
            return RideReadSerializer
        return RideWriteSerializer


class RideEventViewSet(viewsets.ModelViewSet):
    """
    Full CRUD over the assessment's Ride_Event table.

    This is also where a ride's complete event history lives. The ride list
    carries only the last 24 hours, because requirement 4 forbids loading the
    full set, so requirement 3's "related RideEvents" is honoured by linking
    here instead -- filtered by ride, and paginated.
    """

    queryset = RideEvent.objects.all()
    serializer_class = RideEventSerializer
    filterset_fields = ["id_ride"]
    ordering_fields = ["created_at"]
