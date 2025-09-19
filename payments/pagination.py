from rest_framework.pagination import CursorPagination

class BookingCursorPagination(CursorPagination):
    page_size = 10  # Default items per page
    ordering = '-updated_at'  # Sort by updated_at descending
    cursor_query_param = 'cursor'  # Optional, default is 'cursor'

class TransactionCursorPagination(CursorPagination):
    page_size = 10  # number of records per page
    ordering = '-created_at'  # cursor ordering