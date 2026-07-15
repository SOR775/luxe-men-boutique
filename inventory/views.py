from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, F
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from .models import Stock, StockMovement, Warehouse


class InventoryDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'inventory/admin_dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Per-warehouse summary
        warehouses = Warehouse.objects.filter(is_active=True)
        summary = []
        for w in warehouses:
            total_qty = Stock.objects.filter(warehouse=w).aggregate(total=Sum('quantity'))['total'] or 0
            low_count = Stock.objects.filter(warehouse=w, quantity__lte=F('low_stock_threshold')).count()
            summary.append({'warehouse': w, 'total_qty': total_qty, 'low_count': low_count})

        ctx['warehouse_summary'] = summary

        # Global low-stock items
        low_items = Stock.objects.filter(quantity__lte=F('low_stock_threshold')).select_related('variant', 'warehouse')[:50]
        ctx['low_items'] = low_items
        return ctx


class InventorySkuManagementView(LoginRequiredMixin, TemplateView):
    template_name = 'inventory/admin_sku_management.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from products.models import ProductVariant

        variants = ProductVariant.objects.select_related('product').prefetch_related('stock_levels').order_by('sku')
        sku_rows = []
        for variant in variants:
            stock_levels = list(variant.stock_levels.all())
            total_stock = sum(stock.quantity for stock in stock_levels)
            low_stock = any(stock.quantity <= stock.low_stock_threshold for stock in stock_levels)
            sku_rows.append({
                'variant': variant,
                'total_stock': total_stock,
                'low_stock': low_stock,
                'warehouses': stock_levels,
            })
        context['sku_rows'] = sku_rows
        return context


class InventoryStockHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'inventory/admin_stock_history.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        history = StockMovement.objects.select_related('stock__variant__product', 'created_by').all()[:200]
        context['history'] = history
        return context


class InventoryLowStockAlertView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        from notifications.models import Notification

        low_items = Stock.objects.filter(quantity__lte=F('low_stock_threshold')).select_related('variant__product')
        staff_users = get_user_model().objects.filter(is_active=True, is_staff=True)
        sent_count = 0
        if low_items.exists():
            for staff in staff_users:
                try:
                    Notification.create(
                        user=staff,
                        title='Low stock alert',
                        message=f'There are {low_items.count()} SKUs at or below their low stock threshold.',
                        target_url='/inventory/admin/dashboard/',
                        level=Notification.Level.WARNING,
                        send_sms=False,
                    )
                    sent_count += 1
                except Exception:
                    pass
        messages.success(request, f'Low stock alerts sent to {sent_count} staff members.')
        return redirect('inventory:admin_dashboard')
# inventory/views.py

