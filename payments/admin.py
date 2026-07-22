from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Payment, MpesaTransaction, MpesaWebhookLog, Refund, PaymentProof


class MpesaTransactionInline(admin.StackedInline):
    model = MpesaTransaction
    extra = 0
    readonly_fields = ('merchant_request_id', 'checkout_request_id', 'response_code',
                       'mpesa_receipt_number', 'transaction_date', 'callback_raw',
                       'created_at', 'updated_at')


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'method', 'amount', 'currency', 'status', 'reference', 'created_at')
    list_filter = ('method', 'status', 'currency')
    search_fields = ('order__order_number', 'reference')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MpesaTransactionInline, RefundInline]


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = ('checkout_request_id', 'phone_number', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('status',)
    search_fields = ('checkout_request_id', 'mpesa_receipt_number', 'phone_number')
    readonly_fields = ('merchant_request_id', 'checkout_request_id', 'callback_raw', 'created_at', 'updated_at')
    actions = ['action_sync_with_mpesa']

    @admin.action(description='🔄 Sync status with Safaricom M-Pesa')
    def action_sync_with_mpesa(self, request, queryset):
        from .mpesa import mpesa_client
        from orders.models import Order, OrderEvent
        synced = 0
        for txn in queryset:
            if not txn.checkout_request_id:
                continue
            res = mpesa_client.stk_query(txn.checkout_request_id)
            code = str(res.get('ResultCode', ''))
            if code == '0':
                txn.status = MpesaTransaction.Status.SUCCESS
                txn.result_code = code
                txn.result_description = res.get('ResultDesc', '')
                txn.save()
                txn.payment.status = Payment.Status.COMPLETED
                txn.payment.save()
                order = txn.payment.order
                order.payment_status = Order.PaymentStatus.PAID
                order.status = Order.Status.ESCROW
                order.save(update_fields=['payment_status', 'status', 'updated_at'])
                OrderEvent.objects.create(
                    order=order,
                    message=f"Synced via admin with M-Pesa: {res.get('ResultDesc', 'Paid')}",
                    created_by=request.user,
                )
                synced += 1
            elif code in ['1032', '1', '1001', '1037', '1025', '9999', '1019']:
                txn.status = MpesaTransaction.Status.FAILED
                txn.result_code = code
                txn.result_description = res.get('ResultDesc', '')
                txn.save()
                txn.payment.status = Payment.Status.FAILED
                txn.payment.save()
        self.message_user(request, f'{synced} transaction(s) verified & synced with M-Pesa as PAID/ESCROW.')


@admin.register(MpesaWebhookLog)
class MpesaWebhookLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'ip_address', 'processed', 'created_at')
    list_filter = ('processed',)
    readonly_fields = ('url', 'headers', 'body', 'ip_address', 'created_at')


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('payment', 'amount', 'status', 'approved_by', 'processed_at', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        if obj.status == Refund.Status.APPROVED and not obj.approved_by:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    list_display = ('order_link', 'uploaded_by', 'mpesa_code', 'status', 'image_preview', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order__order_number', 'mpesa_code', 'uploaded_by__email')
    readonly_fields = ('uploaded_by', 'order', 'created_at', 'updated_at', 'image_preview', 'reviewed_by', 'reviewed_at')
    fieldsets = (
        ('Submission', {'fields': ('order', 'uploaded_by', 'mpesa_code', 'image_preview', 'image', 'notes', 'created_at')}),
        ('Review', {'fields': ('status', 'admin_notes', 'reviewed_by', 'reviewed_at')}),
    )
    actions = ['approve_proofs', 'reject_proofs']

    def order_link(self, obj):
        return format_html('<a href="/admin/orders/order/{}/change/">{}</a>', obj.order.id, obj.order.order_number)
    order_link.short_description = 'Order'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<a href="{}" target="_blank"><img src="{}" style="max-height:120px;max-width:200px;border-radius:4px;"></a>', obj.image.url, obj.image.url)
        return '—'
    image_preview.short_description = 'Image'

    def approve_proofs(self, request, queryset):
        queryset.update(status=PaymentProof.Status.APPROVED, reviewed_by=request.user, reviewed_at=timezone.now())
    approve_proofs.short_description = '✅ Approve selected payment proofs'

    def reject_proofs(self, request, queryset):
        queryset.update(status=PaymentProof.Status.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now())
    reject_proofs.short_description = '❌ Reject selected payment proofs'

    def save_model(self, request, obj, form, change):
        if obj.status in [PaymentProof.Status.APPROVED, PaymentProof.Status.REJECTED]:
            if not obj.reviewed_by:
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
