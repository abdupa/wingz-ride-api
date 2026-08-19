from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter


class StrictOrderingFilter(OrderingFilter):
    """
    DRF's OrderingFilter with two changes, both about silent wrongness.

    **Unknown fields raise instead of being dropped.** By default DRF discards
    ordering terms it does not recognise and carries on, so ?ordering=pickup_tim
    returns a 200 with unsorted data. The typo is invisible: the response looks
    fine, it is just in the wrong order. This returns 400 and names the field.

    **Every ordering ends in the primary key.** PostgreSQL makes no promise
    about the relative order of rows that tie on the sort column, and it is
    free to answer differently for each query. Since each page is its own
    query, a tie means a row can appear on two pages while another is never
    returned -- with the counts still adding up. Appending a unique column
    makes the order total, and the problem disappears.
    """

    def remove_invalid_fields(self, queryset, fields, view, request):
        valid = super().remove_invalid_fields(queryset, fields, view, request)
        if len(valid) == len(fields):
            return valid

        allowed = sorted(
            name
            for name, _label in self.get_valid_fields(queryset, view, {"request": request})
        )
        kept = {term.lstrip("-") for term in valid}
        rejected = sorted({term.lstrip("-") for term in fields} - kept)
        raise ValidationError(
            {
                "ordering": (
                    f"Cannot order by {', '.join(rejected)}. "
                    f"Available: {', '.join(allowed)}."
                )
            }
        )

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering

        primary_key = queryset.model._meta.pk.name
        if not any(term.lstrip("-") == primary_key for term in ordering):
            ordering = list(ordering) + [primary_key]
        return ordering
