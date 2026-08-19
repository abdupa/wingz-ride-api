import django_filters

from .models import Ride


class RideFilter(django_filters.FilterSet):
    """
    Requirement 3: filter the ride list by status and by rider email.

    status is a ChoiceFilter rather than a plain CharFilter so an unknown value
    returns a 400 naming the problem, instead of an empty list that reads as
    "no rides matched".
    """

    status = django_filters.ChoiceFilter(
        choices=Ride.Status.choices,
        label="Ride status",
    )
    rider_email = django_filters.CharFilter(
        method="filter_rider_email",
        label="Rider email",
    )

    class Meta:
        model = Ride
        fields = ["status", "rider_email"]

    def filter_rider_email(self, queryset, name, value):
        # Emails are lowercased when written, so matching the lowercased input
        # exactly uses the unique index on email. Matching case-insensitively
        # with iexact would compile to UPPER(email) = ... and force a scan of
        # the whole user table.
        return queryset.filter(id_rider__email=value.strip().lower())
