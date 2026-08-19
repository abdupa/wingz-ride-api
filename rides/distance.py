"""
Great-circle distance from a caller-supplied point to each ride's pickup.

The maths runs in the database, not in Python. Requirement 3 says pagination
must still work when sorting is applied -- and sorting a page after fetching it
sorts twenty rows out of however many exist, which is not a wrong order so much
as a wrong answer.
"""

from django.db.models import ExpressionWrapper, F, FloatField, Value
from django.db.models.functions import ATan2, Cos, Power, Radians, Sin, Sqrt
from rest_framework import serializers

# IUGG mean earth radius.
EARTH_RADIUS_KM = 6371.0088


def _float(expression):
    return ExpressionWrapper(expression, output_field=FloatField())


def haversine_km(latitude, longitude):
    """
    Haversine rather than the spherical law of cosines.

    The law of cosines is shorter, but it takes acos() of a value approaching 1
    for nearby points, where floating point precision collapses -- two rides a
    few metres apart can come out as zero, or as noise. Haversine stays stable
    at small distances, which is the case that matters when you are sorting by
    proximity.
    """
    lat1 = Radians(Value(float(latitude), output_field=FloatField()))
    lng1 = Radians(Value(float(longitude), output_field=FloatField()))
    lat2 = Radians(F("pickup_latitude"))
    lng2 = Radians(F("pickup_longitude"))

    half_delta_lat = _float((lat2 - lat1) / Value(2.0))
    half_delta_lng = _float((lng2 - lng1) / Value(2.0))

    a = _float(
        Power(Sin(half_delta_lat), Value(2.0))
        + Cos(lat1) * Cos(lat2) * Power(Sin(half_delta_lng), Value(2.0))
    )

    return _float(
        Value(2.0 * EARTH_RADIUS_KM)
        * ATan2(Sqrt(a), Sqrt(_float(Value(1.0) - a)))
    )


class ReferencePointSerializer(serializers.Serializer):
    """
    Validates the ?lat= and ?lng= pair.

    A serializer rather than hand-parsing, so a missing or impossible value
    comes back as a 400 in DRF's usual error shape instead of surfacing as a
    500 from deep inside the ORM.
    """

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
