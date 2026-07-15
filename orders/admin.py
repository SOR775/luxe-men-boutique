from django.contrib import admin
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from payments.models import Payment
from django.utils.html import format_html
from .models import Cart, CartItem, Order, OrderItem, OrderEvent, Coupon, ShippingZone, ShippingRate, ReturnRequest


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'variant_detail', 'sku', 'unit_price', 'quantity', 'line_total')


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 1
    readonly_fields = ('created_at',)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'times_used', 'max_uses', 'valid_until', 'is_active')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)


class ShippingRateInline(admin.TabularInline):
    model = ShippingRate
    extra = 1


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    inlines = [ShippingRateInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'shipping_name', 'total', 'status', 'payment_status', 'delivery_summary', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('order_number', 'shipping_name', 'shipping_email', 'shipping_phone', 'delivery_location_note')
    readonly_fields = ('order_number', 'subtotal', 'total', 'created_at', 'updated_at', 'delivery_location_summary', 'delivery_location_map_link')
    inlines = [OrderItemInline, OrderEventInline]
    actions = ['action_reconcile_payments']

    def delivery_location_summary(self, obj):
        if obj.delivery_latitude is not None and obj.delivery_longitude is not None:
            return f"{obj.delivery_latitude}, {obj.delivery_longitude}"
        return '-'
    delivery_location_summary.short_description = 'Delivery pin'

    def delivery_summary(self, obj):
        pin = f"{obj.delivery_latitude}, {obj.delivery_longitude}" if obj.delivery_latitude is not None and obj.delivery_longitude is not None else '-'
        note = obj.delivery_location_note[:40] if obj.delivery_location_note else '-'
        return f"Pin: {pin} | Note: {note}"
    delivery_summary.short_description = 'Delivery'

    def delivery_location_map_link(self, obj):
        if obj.delivery_latitude is not None and obj.delivery_longitude is not None:
            url = f'https://www.google.com/maps?q={obj.delivery_latitude},{obj.delivery_longitude}'
            return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Open in Google Maps</a>', url)
        return '-'
    delivery_location_map_link.short_description = 'Map'

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, OrderEvent) and not instance.pk:
                instance.created_by = request.user
            instance.save()
        formset.save_m2m()

    @admin.action(description='🔁 Reconcile selected orders (mark PAID if covered)')
    def action_reconcile_payments(self, request, queryset):
        count = 0
        for order in queryset:
            try:
                paid_agg = Payment.objects.filter(order=order).exclude(status=Payment.Status.FAILED).aggregate(total_paid=Sum('amount'))
                paid = paid_agg.get('total_paid') or Decimal('0')
                if paid >= order.total:
                    with transaction.atomic():
                        p = Payment.objects.filter(order=order).exclude(status=Payment.Status.FAILED).order_by('-created_at').first()
                        if p and p.status != Payment.Status.COMPLETED:
                            p.status = Payment.Status.COMPLETED
                            p.save()
                        order.payment_status = order.PaymentStatus.PAID
                        order.status = order.Status.ESCROW
                        order.save(update_fields=['payment_status', 'status', 'updated_at'])
                        OrderEvent.objects.create(
                            order=order,
                            message='Reconciled by admin: payments cover order total; marked PAID and moved to ESCROW.',
                            created_by=request.user,
                        )
                        count += 1
                else:
                    self.message_user(request, f'Order {order.order_number} not reconciled: paid KES {paid} / KES {order.total}', level='warning')
            except Exception as exc:
                self.message_user(request, f'Order {order.order_number} reconciliation failed: {exc}', level='error')
        self.message_user(request, f'{count} order(s) reconciled and moved to PAID/ESCROW.')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session_key', 'total_items', 'subtotal', 'updated_at')
    search_fields = ('user__email', 'session_key')


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('order', 'user', 'type', 'status', 'created_at')
    list_filter = ('type', 'status')
    actions = ['action_complete_return_and_credit_wallet']

    @admin.action(description='💳 Complete return and credit wallet')
    def action_complete_return_and_credit_wallet(self, request, queryset):
        count = 0
        for return_request in queryset:
            try:
                return_request.complete(actor=request.user)
                count += 1
            except Exception as exc:
                self.message_user(request, f'{return_request.id}: {exc}', level='error')
        self.message_user(request, f'{count} return request(s) completed and credited to wallet.')
