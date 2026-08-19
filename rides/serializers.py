from django.urls import reverse
from rest_framework import serializers

from users.serializers import UserSerializer

from .models import Ride, RideEvent


class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideEvent
        fields = ["id_ride_event", "id_ride", "description", "created_at"]


class RideReadSerializer(serializers.ModelSerializer):
    """
    Read shape. Rider and driver are nested in full, as requirement 3 asks.

    Nested serializers are read-only in DRF, which is why writes use a
    separate class rather than one serializer trying to do both jobs.

    todays_ride_events is a plain list attribute placed on each Ride by the
    ViewSet's Prefetch(to_attr=...). It is deliberately NOT a
    SerializerMethodField calling .filter(): that returns identical JSON and
    costs one query per ride, which no correctness test would ever catch.
    """

    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)
    todays_ride_events = RideEventSerializer(many=True, read_only=True)
    ride_events_url = serializers.SerializerMethodField()
    # Present only when the caller supplied a reference point. Named for its
    # unit; the ordering parameter is the plainer "distance".
    distance_km = serializers.FloatField(source="distance", read_only=True, default=None)

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "id_rider",
            "id_driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "todays_ride_events",
            "ride_events_url",
            "distance_km",
        ]

    def to_representation(self, ride):
        data = super().to_representation(ride)
        # Without a reference point there is no distance to report, and a field
        # that is always null except when sorting is noise on every response.
        if data.get("distance_km") is None:
            data.pop("distance_km", None)
        return data

    def get_ride_events_url(self, ride):
        """
        Requirement 3 says each ride must include its related RideEvents;
        requirement 4 says the SQL must never load the full list. Both cannot
        hold. The 24-hour window is returned as data, and the complete history
        is linked rather than inlined -- which loads nothing and costs no query.
        """
        return f"{reverse('rideevent-list')}?id_ride={ride.id_ride}"


class RideWriteSerializer(serializers.ModelSerializer):
    """
    Write shape: rider and driver arrive as plain ids.

    Coordinate bounds are validated here as well as in the database. The check
    constraints are the guarantee; these turn a violation into a readable 400
    instead of an IntegrityError surfacing as a 500.
    """

    pickup_latitude = serializers.FloatField(min_value=-90, max_value=90)
    pickup_longitude = serializers.FloatField(min_value=-180, max_value=180)
    dropoff_latitude = serializers.FloatField(min_value=-90, max_value=90)
    dropoff_longitude = serializers.FloatField(min_value=-180, max_value=180)

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "id_rider",
            "id_driver",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
        ]
