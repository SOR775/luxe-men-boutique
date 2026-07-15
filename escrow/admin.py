"""
escrow/admin.py — Django Admin for Escrow Management
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import EscrowTransaction, EscrowEvent


class EscrowEventInline(admin.TabularInline):
    model = EscrowEvent
    extra = 0
    readonly_fields = ('created_at', 'actor', 'message')
    can_delete = False
    ordering = ('created_at',)


@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'short_id', 'order_link', 'buyer_email', 'amount_display',
        'status_badge', 'created_at', 'release_after', 'days_left',
    )
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('order__order_number', 'buyer__email', 'tracking_number')
    readonly_fields = (
        'id', 'order', 'payment', 'buyer', 'amount', 'currency',
        'created_at', 'updated_at', 'seller_shipped_at', 'buyer_confirmed_at',
        'dispute_opened_at', 'released_at', 'refunded_at',
    )
    fieldsets = (
        ('Core', {
            'fields': ('id', 'order', 'payment', 'buyer', 'amount', 'currency', 'status'),
        }),
        ('Shipment', {
            'fields': ('tracking_number', 'courier', 'seller_shipped_at', 'release_after'),
        }),
        ('Buyer Confirmation', {
            'fields': ('buyer_confirmed_at',),
        }),
        ('Dispute', {
            'fields': ('dispute_reason', 'dispute_evidence', 'dispute_opened_at'),
        }),
        ('Resolution', {
            'fields': ('resolved_by', 'admin_resolution_notes', 'released_at', 'refunded_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    inlines = [EscrowEventInline]
    actions = ['action_release_funds', 'action_refund_buyer', 'action_auto_release']

    def short_id(self, obj):
        return str(obj.id)[:8]
    short_id.short_description = 'ID'

    def order_link(self, obj):
        return format_html(
            '<a href="/admin/orders/order/{}/change/">#{}</a>',
            obj.order.id, obj.order.order_number
        )
    order_link.short_description = 'Order'

    def buyer_email(self, obj):
        return obj.buyer.email if obj.buyer else '(Guest)'
    buyer_email.short_description = 'Buyer'

    def amount_display(self, obj):
        return f'{obj.currency} {obj.amount:,.2f}'
    amount_display.short_description = 'Amount Held'

    def status_badge(self, obj):
        colours = {
            'funded':    '#3b82f6',
            'shipped':   '#f59e0b',
            'delivered': '#10b981',
            'released':  '#6b7280',
            'disputed':  '#ef4444',
            'refunded':  '#8b5cf6',
            'cancelled': '#374151',
        }
        colour = colours.get(obj.status, '#000')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def days_left(self, obj):
        d = obj.days_until_auto_release
        if d is None:
            return '—'
        if d == 0:
            return format_html('<span style="color:red">⚠ Overdue</span>')
        return f'{d}d'
    days_left.short_description = 'Auto-Release'

    @admin.action(description='✅ Release funds to seller')
    def action_release_funds(self, request, queryset):
        count = 0
        for escrow in queryset:
            try:
                escrow.release_funds(actor=request.user, notes='Admin manual release.')
                count += 1
            except ValueError as e:
                self.message_user(request, f'Escrow {escrow.id}: {e}', level='error')
        self.message_user(request, f'{count} escrow(s) released.')

    @admin.action(description='💸 Release funds and credit buyer wallet')
    def action_release_and_credit_wallet(self, request, queryset):
        count = 0
        for escrow in queryset:
            try:
                escrow.release_funds(actor=request.user, notes='Admin manual release with wallet credit.')
                count += 1
            except ValueError as e:
                self.message_user(request, f'Escrow {escrow.id}: {e}', level='error')
        self.message_user(request, f'{count} escrow(s) processed and wallet credited.')

    @admin.action(description='🔄 Refund buyer (resolve dispute)')
    def action_refund_buyer(self, request, queryset):
        count = 0
        for escrow in queryset:
            try:
                escrow.refund_buyer(actor=request.user, notes='Admin refund decision.')
                count += 1
            except ValueError as e:
                self.message_user(request, f'Escrow {escrow.id}: {e}', level='error')
        self.message_user(request, f'{count} escrow(s) refunded.')

    @admin.action(description='⏰ Run auto-release check now')
    def action_auto_release(self, request, queryset):
        from escrow.tasks import auto_release_expired_escrows
        released = auto_release_expired_escrows()
        self.message_user(request, f'Auto-release complete: {released} escrow(s) released.')


@admin.register(EscrowEvent)
class EscrowEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'escrow', 'actor', 'short_message')
    list_filter = ('created_at',)
    search_fields = ('escrow__order__order_number', 'message', 'actor__email')
    readonly_fields = ('id', 'escrow', 'actor', 'message', 'created_at')

    def short_message(self, obj):
        return obj.message[:80]
    short_message.short_description = 'Message'
