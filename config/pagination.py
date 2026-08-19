from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination


class CappedPageNumberPagination(PageNumberPagination):
    """
    Page-number pagination with a caller-adjustable size and a hard ceiling.

    Cursor pagination would be the better answer for deep paging on a very
    large table -- it never runs a COUNT and does not degrade at high offsets.
    It cannot be used here: it requires a fixed, unique ordering key, and
    requirement 3 lets the caller choose the ordering, including a computed
    distance. So offset paging is the right call precisely because of the
    sorting requirement.

    max_page_size stops a caller asking for a million rows in one request.
    """

    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        """
        DRF ignores an unparseable page_size and quietly serves the default, so
        ?page_size=abc returns 20 rows with a 200 and the caller never learns
        their parameter was discarded. Same failure mode as an ordering typo:
        the response looks right, it just is not what was asked for.
        """
        raw = request.query_params.get(self.page_size_query_param)
        if raw is not None:
            try:
                if int(raw) < 1:
                    raise ValueError
            except ValueError:
                raise ValidationError(
                    {self.page_size_query_param: "Must be a whole number of at least 1."}
                )
        return super().get_page_size(request)
