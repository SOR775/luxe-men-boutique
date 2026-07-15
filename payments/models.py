"""
payments/models.py — M-Pesa Daraja, Transaction, Payment Records
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    """
    Master payment record tied to an order.
    Supports M-Pesa, Bank Transfer, Cash on Delivery.
    """
    class Method(models.TextChoices):
        MPESA       = 'mpesa',       _('M-Pesa')
        BANK        = 'bank',        _('Bank Transfer')
        COD         = 'cod',         _('Cash on Delivery')
        CARD        = 'card',        _('Card')
        WALLET      = 'wallet',      _('Wallet')

    class Status(models.TextChoices):
        PENDING     = 'pending',     _('Pending')
        PROCESSING  = 'processing',  _('Processing')
        COMPLETED   = 'completed',   _('Completed')
        FAILED      = 'failed',      _('Failed')
        CANCELLED   = 'cancelled',   _('Cancelled')
        REFUNDED    = 'refunded',    _('Refunded')
        PARTIAL_REFUND = 'partial_refund', _('Partial Refund')

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order       = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payments')
    method      = models.CharField(max_length=10, choices=Method.choices)
    status      = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    currency    = models.CharField(max_length=3, default='KES')
    reference   = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.method.upper()} payment of {self.currency} {self.amount} — {self.status}"


class MpesaTransaction(models.Model):
    """
    Detailed record of an M-Pesa Daraja API STK Push transaction.
    Stores both outbound request data and inbound callback data.
    """
    class Status(models.TextChoices):
        INITIATED   = 'initiated',   _('Initiated')
        PENDING     = 'pending',     _('Pending Confirmation')
        SUCCESS     = 'success',     _('Successful')
        FAILED      = 'failed',      _('Failed')
        CANCELLED   = 'cancelled',   _('Cancelled by User')
        TIMEOUT     = 'timeout',     _('Timed Out')

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment         = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='mpesa_transactions')

    # STK Push request details
    phone_number    = models.CharField(max_length=15)
    amount          = models.DecimalField(max_digits=10, decimal_places=2)
    account_reference = models.CharField(max_length=12)
    transaction_desc  = models.CharField(max_length=13)

    # Daraja API response (request phase)
    merchant_request_id  = models.CharField(max_length=100, blank=True, db_index=True)
    checkout_request_id  = models.CharField(max_length=100, blank=True, unique=True, null=True, db_index=True)
    response_code        = models.CharField(max_length=10, blank=True)
    response_description = models.CharField(max_length=255, blank=True)
    customer_message     = models.CharField(max_length=255, blank=True)

    # Callback payload (confirmation phase)
    result_code         = models.CharField(max_length=10, blank=True)
    result_description  = models.CharField(max_length=255, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True, db_index=True)
    transaction_date    = models.CharField(max_length=20, blank=True)  # Safaricom returns as string
    callback_raw        = models.JSONField(default=dict, blank=True)

    # Internal
    status          = models.CharField(max_length=15, choices=Status.choices, default=Status.INITIATED)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'M-Pesa Transaction'

    def __str__(self):
        return f"M-Pesa {self.checkout_request_id} — {self.status}"

    @property
    def is_complete(self):
        return self.status == self.Status.SUCCESS

    @property
    def is_failed(self):
        return self.status in [self.Status.FAILED, self.Status.CANCELLED, self.Status.TIMEOUT]


class MpesaWebhookLog(models.Model):
    """Raw log of every incoming M-Pesa callback for debugging & auditing."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url         = models.CharField(max_length=200)
    headers     = models.JSONField(default=dict)
    body        = models.JSONField(default=dict)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    processed   = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Webhook at {self.created_at} — processed={self.processed}"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING   = 'pending',   _('Pending')
        APPROVED  = 'approved',  _('Approved')
        PROCESSED = 'processed', _('Processed')
        FAILED    = 'failed',    _('Failed')

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment     = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    reason      = models.TextField()
    status      = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_refunds'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Refund of {self.amount} for Payment {self.payment.id}"


class PaymentProof(models.Model):
    """
    Customer-uploaded payment evidence (screenshot or M-Pesa message)
    submitted when there is a delay in automatic payment confirmation.
    """
    class Status(models.TextChoices):
        PENDING  = 'pending',  _('Pending Review')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order       = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payment_proofs')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='payment_proofs')
    image       = models.ImageField(upload_to='payment_proofs/%Y/%m/', blank=True, null=True)
    mpesa_code  = models.CharField(max_length=20, blank=True, help_text='M-Pesa transaction code e.g. QEK7XXXXX')
    notes       = models.TextField(blank=True, help_text='Any additional notes about the payment')
    status      = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_proofs')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Proof'

    def __str__(self):
        return f"Proof for Order #{self.order.order_number} — {self.status}"
