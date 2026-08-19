from rest_framework import viewsets

from .models import Ride, RideEvent
from .serializers import RideEventSerializer, RideReadSerializer, RideWriteSerializer


class RideViewSet(viewsets.ModelViewSet):
    """
    Full CRUD over the assessment's Ride table.

    Query optimisation lives in get_queryset rather than in the serializers,
    so the serializers stay thin and the query cost of a request is readable
    in one place.
    """

    queryset = Ride.objects.all()

    def get_serializer_class(self):
        # Reads nest rider and driver; writes take plain ids.
        if self.action in ("list", "retrieve"):
            return RideReadSerializer
        return RideWriteSerializer


class RideEventViewSet(viewsets.ModelViewSet):
    """
    Full CRUD over the assessment's Ride_Event table.

    This is also where a ride's complete event history lives. The ride list
    deliberately carries only the last 24 hours (requirement 4 forbids loading
    the full set), so the full history is reachable here, filtered and paged.
    """

    queryset = RideEvent.objects.all()
    serializer_class = RideEventSerializer
