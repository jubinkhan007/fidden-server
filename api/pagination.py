from rest_framework.pagination import CursorPagination

class ServicesCursorPagination(CursorPagination):
    ordering = ('-avg_rating', '-review_count')  # multiple fields, tie-breaker
    cursor_query_param = 'cursor'
    page_size = 10  # default page size if 'top' is not provided

    def get_page_size(self, request):
        """
        Use 'top' query param as page size if provided; otherwise, use default page_size.
        """
        top = request.query_params.get('top')
        if top:
            try:
                return int(top)
            except ValueError:
                return self.page_size  # fallback to default if invalid
        return self.page_size

class GlobalSearchCursorPagination(CursorPagination):
    page_size = 10
    ordering = 'distance'  # will sort later manually in view if needed


class ReviewCursorPagination(CursorPagination):
    page_size = 10
    ordering = "-created_at"  # newest first