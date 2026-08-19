import django_filters
from rest_framework.exceptions import ValidationError

from .distance import haversine_km
from .models import Ride


class RideFilter(django_filters.FilterSet):
    """
    Requirement 3: filter the ride list by status and by rider email, and take
    the reference point that distance sorting needs.

    lat and lng are declared here rather than read straight off the request, so
    they appear in the browsable API's filter form alongside the others and are
    validated by the same machinery. A parameter that only exists in the README
    is a parameter nobody finds.
    """

    status = django_filters.ChoiceFilter(
        choices=Ride.Status.choices,
        label="Ride status",
    )
    rider_email = django_filters.CharFilter(
        method="filter_rider_email",
        label="Rider email",
    )
    # These two do not filter anything. They carry the reference point that
    # filter_queryset turns into a distance annotation below -- declared as
    # filters purely so they are discoverable and validated.
    lat = django_filters.NumberFilter(
        method="carry", min_value=-90, max_value=90,
        label="Reference latitude (for ordering=distance)",
    )
    lng = django_filters.NumberFilter(
        method="carry", min_value=-180, max_value=180,
        label="Reference longitude (for ordering=distance)",
    )

    class Meta:
        model = Ride
        fields = ["status", "rider_email", "lat", "lng"]

    def filter_rider_email(self, queryset, name, value):
        # Emails are lowercased when written, so matching the lowercased input
        # exactly uses the unique index on email. Matching case-insensitively
        # with iexact would compile to UPPER(email) = ... and force a scan of
        # the whole user table.
        return queryset.filter(id_rider__email=value.strip().lower())

    def carry(self, queryset, name, value):
        """A no-op: lat and lng are consumed together in filter_queryset."""
        return queryset

    def filter_queryset(self, queryset):
        """
        Adds the distance annotation once, after the ordinary filters.

        It has to happen here rather than in either filter's own method,
        because the annotation needs both halves of the point and django-filter
        applies filters one at a time. Doing it in the FilterSet also means the
        annotation exists before the ordering backend runs, which is what lets
        ?ordering=distance sort in the database.
        """
        queryset = super().filter_queryset(queryset)

        latitude = self.form.cleaned_data.get("lat")
        longitude = self.form.cleaned_data.get("lng")
        ordering = self.request.query_params.get("ordering", "") if self.request else ""
        wants_distance = "distance" in ordering

        if latitude is None and longitude is None and not wants_distance:
            return queryset

        # Half a point is not a point. Naming the missing half turns
        # ?ordering=distance with no coordinates into a readable 400 rather
        # than a FieldError from inside the ORM.
        missing = {
            name: "Required to order by distance."
            for name, value in (("lat", latitude), ("lng", longitude))
            if value is None
        }
        if missing:
            raise ValidationError(missing)

        return queryset.annotate(distance=haversine_km(latitude, longitude))
