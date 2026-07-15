"""
core/pagination.py — Custom Pagination Classes
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Standard pagination: 24 items per page (grid-friendly)."""
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class LargePagination(PageNumberPagination):
    """For admin list views: 50 items per page."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
