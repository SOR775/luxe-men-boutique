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
    if getattr(request.user, 'is_authenticated', False) and request.user.is_staff:
        if request.user.is_superuser:
            permissions = [
                'access_admin_dashboard',
                'access_orders',
                'access_products',
                'access_inventory_dashboard',
                'access_inventory_sku',
                'access_inventory_stock_history',
                'access_coupons',
                'access_bulk_order_actions',
                'access_rma',
                'access_support_queue',
                'access_user_management',
                'access_audit_log',
                'access_system_health',
                'access_dispute_resolution',
                'access_content_moderation',
                'access_settings',
                'access_wallets',
                'access_wallet_transactions',
                'access_finance',
                'access_payment_review',
                'access_reconciliation',
                'access_escrow',
                'access_analytics',
            ]
        else:
            try:
                from accounts.models import Administrator

                admin_profile, _ = Administrator.objects.get_or_create(user=request.user)
                permissions = list(admin_profile.roles.values_list('permissions__codename', flat=True).distinct())
                extra_permissions = list(admin_profile.extra_permissions.values_list('codename', flat=True))
                permissions.extend(extra_permissions)
                permissions = list(dict.fromkeys(permissions))
            except Exception:
                permissions = []

            if not permissions:
                permissions = [
                    'access_admin_dashboard',
                    'access_support_queue',
                    'access_audit_log',
                    'access_system_health',
                    'access_user_management',
                    'access_dispute_resolution',
                    'access_content_moderation',
                    'access_settings',
                ]
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
