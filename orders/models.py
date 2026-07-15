"""
orders/models.py — Cart, Order, OrderItem, Shipping, Invoice
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


# ─── Coupon / Discount ────────────────────────────────────────────────────────

class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', _('Percentage')
        FIXED = 'fixed', _('Fixed Amount')
        FREE_SHIPPING = 'free_shipping', _('Free Shipping')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, db_index=True)
    discount_type = models.CharField(max_length=15, choices=DiscountType.choices, default=DiscountType.PERCENTAGE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank for unlimited")
    times_used = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_until:
            return False
        if self.max_uses and self.times_used >= self.max_uses:
            return False
        return True

    def compute_discount(self, order_total):
        if not self.is_valid():
            return 0
        if self.discount_type == self.DiscountType.PERCENTAGE:
            return round(order_total * self.discount_value / 100, 2)
        elif self.discount_type == self.DiscountType.FIXED:
            return min(self.discount_value, order_total)
        return 0


# ─── Shipping Zone & Rate ─────────────────────────────────────────────────────

class ShippingZone(models.Model):
    name = models.CharField(max_length=100)
    regions = models.TextField(help_text="Comma-separated list of regions/counties")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ShippingRate(models.Model):
    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name='rates')
    name = models.CharField(max_length=100, help_text="e.g. Standard, Express, Overnight")
    price = models.DecimalField(max_digits=8, decimal_places=2)
    free_above = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                     help_text="Orders above this amount get free shipping")
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=3)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.zone.name} — {self.name} (KES {self.price})"

    @property
    def delivery_estimate(self):
        if self.estimated_days_min == self.estimated_days_max:
            return f"{self.estimated_days_min} day{'s' if self.estimated_days_min > 1 else ''}"
        return f"{self.estimated_days_min}–{self.estimated_days_max} days"


# ─── Cart ─────────────────────────────────────────────────────────────────────

class Cart(models.Model):
    """Session-based cart that can be associated with a user on login."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='carts'
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        owner = self.user.email if self.user else f"session:{self.session_key}"
        return f"Cart ({owner})"

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'variant')

    def __str__(self):
        return f"{self.quantity}x {self.variant}"

    @property
    def unit_price(self):
        return self.variant.final_price

    @property
    def line_total(self):
        return self.unit_price * self.quantity


# ─── Order ────────────────────────────────────────────────────────────────────

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING     = 'pending',     _('Pending')
        PAID        = 'paid',        _('Paid')
        ESCROW      = 'escrow',      _('In Escrow')
        PACKING     = 'packing',     _('Packing')
        SHIPPED     = 'shipped',     _('Shipped')
        DELIVERED   = 'delivered',   _('Delivered')
        COMPLETED   = 'completed',   _('Completed')
        CANCELLED   = 'cancelled',   _('Cancelled')
        RETURNED    = 'returned',    _('Returned')
        REFUNDED    = 'refunded',    _('Refunded')

    class PaymentStatus(models.TextChoices):
        UNPAID      = 'unpaid',      _('Unpaid')
        PAID        = 'paid',        _('Paid')
        PARTIAL     = 'partial',     _('Partially Paid')
        REFUNDED    = 'refunded',    _('Refunded')
        FAILED      = 'failed',      _('Failed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders'
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales'
    )

    # Shipping snapshot (stored to preserve address at time of order)
    shipping_name    = models.CharField(max_length=200)
    shipping_phone   = models.CharField(max_length=20)
    shipping_email   = models.EmailField()
    shipping_address = models.CharField(max_length=300)
    shipping_city    = models.CharField(max_length=100)
    shipping_country = models.CharField(max_length=100, default='Kenya')
    shipping_rate    = models.ForeignKey(ShippingRate, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_location_note = models.CharField(max_length=250, blank=True)

    # Financials
    subtotal          = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost     = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    discount_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total             = models.DecimalField(max_digits=10, decimal_places=2)
    coupon            = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)

    # Status
    status         = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)

    # Notes
    customer_notes = models.TextField(blank=True)
    admin_notes    = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            import random, string
            self.order_number = 'LM' + ''.join(
                random.choices(string.digits, k=8)
            )
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order     = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    variant   = models.ForeignKey('products.ProductVariant', on_delete=models.SET_NULL, null=True)
    # Snapshot at time of purchase
    product_name   = models.CharField(max_length=200)
    variant_detail = models.CharField(max_length=100, blank=True)
    sku            = models.CharField(max_length=50)
    unit_price     = models.DecimalField(max_digits=10, decimal_places=2)
    quantity       = models.PositiveIntegerField()
    line_total     = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product_name} (Order #{self.order.order_number})"


# ─── Order Timeline / Events ──────────────────────────────────────────────────

class OrderEvent(models.Model):
    """Immutable log of status changes and notes for an order."""
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order   = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='events')
    message = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Event on {self.order.order_number}: {self.message[:50]}"


# ─── Return / Refund Request ──────────────────────────────────────────────────

class ReturnRequest(models.Model):
    class Type(models.TextChoices):
        RETURN   = 'return',   _('Return')
        EXCHANGE = 'exchange', _('Exchange')

    class Status(models.TextChoices):
        PENDING  = 'pending',  _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        COMPLETED = 'completed', _('Completed')

    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order  = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='returns')
    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type   = models.CharField(max_length=10, choices=Type.choices)
    reason = models.TextField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    admin_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.type.capitalize()} request for Order #{self.order.order_number}"

    def complete(self, actor=None):
        if self.status == self.Status.COMPLETED:
            return self
        self.status = self.Status.COMPLETED
        self.save(update_fields=['status', 'updated_at'])
        if self.order.user:
            from wallets.models import award_wallet_credit
            award_wallet_credit(
                self.order.user,
                self.order.total,
                description=f'Refund for {self.order.order_number}',
                reference=f'return-{self.id}',
                actor=actor,
            )
        return self
