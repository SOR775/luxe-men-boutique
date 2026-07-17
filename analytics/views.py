import json
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, F
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from escrow.models import EscrowTransaction
from inventory.models import Stock
from notifications.models import Notification
from orders.models import Order, OrderItem, Coupon
from payments.models import Payment
from products.models import Product
from support.models import SupportMessage, SupportTicket
from accounts.models import User


class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return self.handle_no_permission()
        if not (request.user.is_staff or request.user.has_admin_permission('access_admin_dashboard')):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['orders_count'] = Order.objects.count()
        context['total_revenue'] = Order.objects.aggregate(total=Sum('total'))['total'] or 0
        context['customers_count'] = User.objects.count()
        context['products_count'] = Product.objects.filter(visibility=Product.Visibility.PUBLISHED).count()
        context['coupons_count'] = Coupon.objects.count()
        context['orders_by_status'] = dict(Order.objects.values('status').annotate(count=Count('id')).values_list('status', 'count'))

        payment_alert_count = Payment.objects.filter(status__in=[Payment.Status.FAILED, Payment.Status.PENDING, Payment.Status.PROCESSING]).count()
        escrow_alert_count = EscrowTransaction.objects.filter(
            status__in=[
                EscrowTransaction.Status.FUNDED,
                EscrowTransaction.Status.SHIPPED,
                EscrowTransaction.Status.DELIVERED,
                EscrowTransaction.Status.DISPUTED,
            ]
        ).count()
        context['payment_alert_count'] = payment_alert_count
        context['escrow_alert_count'] = escrow_alert_count
        context['low_stock_count'] = Stock.objects.filter(quantity__lte=F('low_stock_threshold')).count()

        today = timezone.now().date()
        revenue_last_7 = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            start = timezone.datetime.combine(day, timezone.datetime.min.time()).replace(tzinfo=timezone.get_current_timezone())
            end = timezone.datetime.combine(day, timezone.datetime.max.time()).replace(tzinfo=timezone.get_current_timezone())
            total = Order.objects.filter(created_at__range=(start, end)).aggregate(total=Sum('total'))['total'] or 0
            revenue_last_7.append({'date': day.isoformat(), 'total': float(total)})

        context['revenue_last_7'] = revenue_last_7
        context['revenue_last_7_json'] = json.dumps(revenue_last_7)

        top_selling = list(
            OrderItem.objects.values('product_name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')[:6]
        )
        context['top_selling'] = top_selling
        context['top_selling_json'] = json.dumps(top_selling)

        open_tickets = SupportTicket.objects.select_related('user').prefetch_related('messages').filter(
            status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.PENDING]
        ).order_by('-updated_at')[:8]
        context['support_tickets'] = list(open_tickets)
        context['support_ticket_messages'] = {
            ticket.pk: list(ticket.messages.order_by('-created_at')[:2])
            for ticket in open_tickets
        }

        context['recent_orders'] = Order.objects.select_related('user').order_by('-created_at')[:10]
        context['notification_count'] = Notification.objects.filter(is_read=False).count()
        return context

