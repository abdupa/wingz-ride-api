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
