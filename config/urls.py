"""
LUXE MEN — Root URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap

# ─── URL Patterns ─────────────────────────────────────────────────────────────
urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    path('dashboard/', include('admin.urls', namespace='dashboard')),

    # Core / Homepage
    path('', include('core.urls', namespace='core')),

    # Accounts (auth, profile, RBAC)
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # Products & Catalog
    path('products/', include('products.urls', namespace='products')),

    # Shopping Cart & Orders
    path('cart/', include('orders.urls', namespace='orders')),
    path('checkout/', include('orders.checkout_urls', namespace='checkout')),

    # Payments
    path('payments/', include('payments.urls', namespace='payments')),

    # Escrow
    path('escrow/', include('escrow.urls', namespace='escrow')),

    # Inventory
    path('inventory/', include('inventory.urls', namespace='inventory')),

    # Marketing
    path('marketing/', include('marketing.urls', namespace='marketing')),
    path('blog/', include('marketing.blog_urls', namespace='blog')),

    # Support
    path('support/', include('support.urls', namespace='support')),

    # Notifications
    path('notifications/', include('notifications.urls', namespace='notifications')),

    # Analytics
    path('analytics/', include('analytics.urls', namespace='analytics')),

    # Wallets
    path('wallet/', include('wallets.urls', namespace='wallets')),

    # REST API
    path('api/', include('api.urls', namespace='api')),
]

# ─── Debug Toolbar ────────────────────────────────────────────────────────────
if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
