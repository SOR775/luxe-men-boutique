"""
core/context_processors.py — Global Template Context
Injects site-wide variables into every template render.
"""
from django.conf import settings


def site_settings(request):
    """Inject global site configuration into all templates."""
    return {
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'LUXE MEN'),
        'SITE_URL': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
        'CURRENCY_CODE': getattr(settings, 'CURRENCY_CODE', 'KES'),
        'CURRENCY_SYMBOL': getattr(settings, 'CURRENCY_SYMBOL', 'KSh'),
    }


def cart_count(request):
    """Inject cart item count for navbar badge."""
    count = 0
    try:
        if request.user.is_authenticated:
            from orders.models import Cart
            cart = Cart.objects.filter(user=request.user, is_active=True).first()
            if cart:
                count = cart.items.count()
        else:
            cart_id = request.session.get('cart_id')
            if cart_id:
                from orders.models import Cart
                cart = Cart.objects.filter(id=cart_id, is_active=True).first()
                if cart:
                    count = cart.items.count()
    except Exception:
        pass
    return {'cart_count': count}


def notifications_count(request):
    """Inject unread notification count for navbar badge."""
    count = 0
    try:
        if request.user.is_authenticated:
            from notifications.models import Notification
            count = Notification.objects.filter(
                user=request.user, is_read=False
            ).count()
    except Exception:
        pass
    return {'notifications_count': count}


def admin_permissions(request):
    """Expose the current user's admin permission codename set to templates."""
    permissions = []
    if getattr(request.user, 'is_authenticated', False):
        try:
            if request.user.is_staff:
                permissions = list(request.user.admin_profile.roles.values_list('permissions__codename', flat=True).distinct())
                extra_permissions = list(request.user.admin_profile.extra_permissions.values_list('codename', flat=True))
                permissions.extend(extra_permissions)
                permissions = list(dict.fromkeys(permissions))
        except Exception:
            permissions = []
    return {'user_admin_permissions': permissions}


def returning_customer_banner(request):
    """Show a lightweight welcome-back prompt for returning authenticated users."""
    if not getattr(request.user, 'is_authenticated', False):
        return {
            'show_returning_customer_banner': False,
            'show_recently_viewed_banner': False,
        }

    try:
        from orders.models import Order
        has_purchases = Order.objects.filter(user=request.user).exists()
    except Exception:
        has_purchases = False

    recently_viewed = []
    try:
        recently_viewed = request.session.get('recently_viewed', []) or []
        if isinstance(recently_viewed, str):
            recently_viewed = [recently_viewed]
    except Exception:
        recently_viewed = []

    return {
        'show_returning_customer_banner': has_purchases,
        'returning_customer_message': 'Welcome back — your saved favorites and recent orders are ready when you are.' if has_purchases else False,
        'show_recently_viewed_banner': bool(recently_viewed),
    }
