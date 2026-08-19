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
    """

    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)

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
