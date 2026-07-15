"""
core/middleware.py — Custom Security & Activity Middleware
"""
import logging
import time
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Injects security headers into every HTTP response.
    Provides XSS, clickjacking, and content-type sniffing protection.
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        return response


class ActivityLogMiddleware(MiddlewareMixin):
    """
    Logs all incoming requests with timing information.
    Tracks authenticated user activity for audit purposes.
    """

    def process_request(self, request: HttpRequest) -> None:
        request._start_time = time.time()

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if hasattr(request, '_start_time'):
            duration = (time.time() - request._start_time) * 1000  # ms
            user = request.user.username if request.user.is_authenticated else 'anonymous'
            if not request.path.startswith('/static/') and not request.path.startswith('/media/'):
                logger.debug(
                    f'{request.method} {request.path} | {response.status_code} | '
                    f'{duration:.2f}ms | user={user}'
                )
        return response


class CartMiddleware(MiddlewareMixin):
    """
    Ensures a cart session key exists for every visitor.
    Enables both anonymous and authenticated cart management.
    """

    def process_request(self, request: HttpRequest) -> None:
        if 'cart_id' not in request.session:
            request.session['cart_id'] = None
