import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model


def _notify_back_in_stock(stock):
    if not stock.variant.product.visibility == 'published':
        return

    from products.models import WishlistItem
    from notifications.models import Notification

    wishlist_items = WishlistItem.objects.filter(product=stock.variant.product).select_related('user')
    for item in wishlist_items:
        user = item.user
        if not user.is_active:
            continue
        try:
            Notification.create(
                user=user,
                title=f'{stock.variant.product.name} is back in stock',
                message=f'The item you wishlisted is available again. Add it to your cart before it sells out.',
                target_url=stock.variant.product.get_absolute_url() if hasattr(stock.variant.product, 'get_absolute_url') else '',
                level=Notification.Level.SUCCESS,
                send_sms=True,
            )
        except Exception:
            pass

class Warehouse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Stock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.CASCADE, related_name='stock_levels')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stocks')
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('variant', 'warehouse')
        verbose_name_plural = 'Stock Levels'

    def __str__(self):
        return f"{self.variant.product.name} ({self.variant.sku}) - {self.quantity} at {self.warehouse.name}"

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.quantity == 0


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        PURCHASE = 'purchase', _('Purchase (In)')
        RETURN = 'return', _('Return (In)')
        TRANSFER_IN = 'transfer_in', _('Transfer (In)')
        SALE = 'sale', _('Sale (Out)')
        DAMAGE = 'damage', _('Damage/Loss (Out)')
        TRANSFER_OUT = 'transfer_out', _('Transfer (Out)')
        ADJUSTMENT = 'adjustment', _('Manual Adjustment')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.IntegerField(help_text="Positive for additions, negative for reductions")
    reference = models.CharField(max_length=100, blank=True, help_text="Order ID, PO Number, etc.")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='stock_movements_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        # Validate that the quantity reduces stock appropriately
        if self.quantity < 0 and abs(self.quantity) > self.stock.quantity:
            raise ValidationError("Stock movement would result in negative inventory.")

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        was_out_of_stock = self.stock.quantity == 0
        super().save(*args, **kwargs)
        
        # Update the actual stock quantity only when the movement is first created
        if is_new:
            self.stock.quantity += self.quantity
            self.stock.save(update_fields=['quantity', 'last_updated'])
            if was_out_of_stock and self.quantity > 0:
                _notify_back_in_stock(self.stock)

    def __str__(self):
        return f"{self.movement_type} of {self.quantity} for {self.stock.variant.sku}"

