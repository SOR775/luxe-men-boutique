"""
escrow/models.py — Escrow Transaction & Audit Log

State Machine:
  FUNDED → SHIPPED → DELIVERED → RELEASED
                              ↘ DISPUTED → RELEASED (admin)
                                        ↘ REFUNDED  (admin)
  Any state → CANCELLED (admin only, pre-ship)
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from orders.models import Order


class EscrowTransaction(models.Model):
    """
    Holds buyer funds securely until both parties confirm the transaction.
    One escrow per order.
    """

    class Status(models.TextChoices):
        FUNDED    = 'funded',    _('Funded — Awaiting Shipment')
        SHIPPED   = 'shipped',   _('Shipped — Awaiting Buyer Confirmation')
        DELIVERED = 'delivered', _('Delivered — Pending Release')
        RELEASED  = 'released',  _('Released — Funds Sent to Seller')
        DISPUTED  = 'disputed',  _('Disputed — Under Review')
        REFUNDED  = 'refunded',  _('Refunded — Funds Returned to Buyer')
        CANCELLED = 'cancelled', _('Cancelled')

    # Core links
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order   = models.OneToOneField(
        'orders.Order', on_delete=models.CASCADE, related_name='escrow'
    )
    payment = models.OneToOneField(
        'payments.Payment', on_delete=models.CASCADE, related_name='escrow'
    )
    buyer   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='escrow_purchases'
    )

    # Financials
    amount   = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')

    # Status
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.FUNDED, db_index=True
    )

    # Shipment
    tracking_number   = models.CharField(max_length=100, blank=True)
    courier           = models.CharField(max_length=100, blank=True)
    seller_shipped_at = models.DateTimeField(null=True, blank=True)
    release_after     = models.DateTimeField(
        null=True, blank=True,
        help_text='Auto-release funds to seller after this datetime if buyer does not respond.'
    )

    # Buyer confirmation
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Dispute
    dispute_reason      = models.TextField(blank=True)
    dispute_opened_at   = models.DateTimeField(null=True, blank=True)
    dispute_evidence    = models.TextField(blank=True, help_text='URLs or descriptions of evidence')

    # Resolution
    resolved_by            = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='escrow_resolutions'
    )
    admin_resolution_notes = models.TextField(blank=True)
    released_at            = models.DateTimeField(null=True, blank=True)
    refunded_at            = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Escrow Transaction'
        verbose_name_plural = 'Escrow Transactions'

    def __str__(self):
        return f'Escrow #{str(self.id)[:8]} — {self.get_status_display()} — {self.currency} {self.amount}'

    # ── Business logic ────────────────────────────────────────────────────────

    AUTO_RELEASE_DAYS = getattr(settings, 'ESCROW_AUTO_RELEASE_DAYS', 7)

    def mark_shipped(self, tracking_number='', courier='', actor=None):
        """Seller (or admin) confirms dispatch."""
        if self.status != self.Status.FUNDED:
            raise ValueError(f'Cannot mark shipped from status: {self.status}')
        self.status           = self.Status.SHIPPED
        self.tracking_number  = tracking_number
        self.courier          = courier
        self.seller_shipped_at = timezone.now()
        self.release_after    = timezone.now() + timedelta(days=self.AUTO_RELEASE_DAYS)
        self.save()
        self._log(f'Order marked as shipped. Tracking: {tracking_number or "N/A"}. '
                  f'Auto-release scheduled for {self.release_after.strftime("%d %b %Y %H:%M")} UTC.',
                  actor=actor)

    def buyer_confirm(self, actor=None):
        """Buyer confirms receipt — marks delivery and awaits final release."""
        if self.status != self.Status.SHIPPED:
            raise ValueError(f'Cannot confirm receipt from status: {self.status}')
        self.status             = self.Status.DELIVERED
        self.buyer_confirmed_at = timezone.now()
        self.save()
        self.order.status = Order.Status.DELIVERED
        self.order.save(update_fields=['status'])
        self._log('Buyer confirmed receipt of goods and marked order as delivered.', actor=actor)

    def release_funds(self, actor=None, notes=''):
        """Release held funds to seller (buyer final approval, admin action, or auto-release)."""
        allowed = {self.Status.DELIVERED, self.Status.DISPUTED, self.Status.SHIPPED}
        if self.status not in allowed:
            raise ValueError(f'Cannot release funds from status: {self.status}')
        self.status      = self.Status.RELEASED
        self.released_at = timezone.now()
        if notes:
            self.admin_resolution_notes = notes
        if actor and hasattr(actor, 'is_staff') and actor.is_staff:
            self.resolved_by = actor
        self.save()
        # Update order status
        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=['status'])
        # Credit the SELLER's wallet, not the buyer's
        seller = self.order.seller
        if seller:
            from wallets.models import award_wallet_credit
            award_wallet_credit(
                seller,
                self.amount,
                description=f'Order #{self.order.order_number} payment released',
                reference=f'escrow-{self.id}',
                actor=actor,
                order=self.order,
            )
        self._log(
            f'Escrow released. Funds of {self.currency} {self.amount} marked for payout to seller.',
            actor=actor
        )

    def open_dispute(self, reason, evidence='', actor=None):
        """Buyer opens a dispute."""
        if self.status not in {self.Status.SHIPPED, self.Status.DELIVERED}:
            raise ValueError(f'Cannot open dispute from status: {self.status}')
        self.status           = self.Status.DISPUTED
        self.dispute_reason   = reason
        self.dispute_evidence = evidence
        self.dispute_opened_at = timezone.now()
        self.save()
        self._log(f'Dispute opened by buyer. Reason: {reason[:100]}', actor=actor)

    def refund_buyer(self, actor=None, notes=''):
        """Admin resolves dispute in buyer's favour."""
        if self.status != self.Status.DISPUTED:
            raise ValueError(f'Cannot refund from status: {self.status}')
        self.status      = self.Status.REFUNDED
        self.refunded_at = timezone.now()
        if notes:
            self.admin_resolution_notes = notes
        if actor:
            self.resolved_by = actor
        self.save()
        # Update order status
        self.order.status         = 'refunded'
        self.order.payment_status = 'refunded'
        self.order.save(update_fields=['status', 'payment_status'])
        if self.buyer:
            from wallets.models import award_wallet_credit
            award_wallet_credit(
                self.buyer,
                self.amount,
                description=f'Escrow refund for order {self.order.order_number}',
                reference=f'escrow-refund-{self.id}',
                actor=actor,
                order=self.order,
            )
        self._log(f'Dispute resolved: buyer refunded {self.currency} {self.amount}.', actor=actor)

    def cancel(self, actor=None, reason=''):
        """Admin cancels escrow (only before shipment)."""
        if self.status not in {self.Status.FUNDED}:
            raise ValueError(f'Cannot cancel from status: {self.status}')
        self.status = self.Status.CANCELLED
        self.save()
        self._log(f'Escrow cancelled. Reason: {reason or "No reason given."}', actor=actor)

    @property
    def is_active(self):
        return self.status in {
            self.Status.FUNDED, self.Status.SHIPPED,
            self.Status.DELIVERED, self.Status.DISPUTED,
        }

    @property
    def is_auto_releasable(self):
        """True if auto-release timer has expired and status is still SHIPPED."""
        return (
            self.status == self.Status.SHIPPED
            and self.release_after is not None
            and timezone.now() >= self.release_after
        )

    @property
    def days_until_auto_release(self):
        if self.release_after and self.status == self.Status.SHIPPED:
            delta = self.release_after - timezone.now()
            return max(0, delta.days)
        return None

    def _log(self, message, actor=None):
        EscrowEvent.objects.create(
            escrow=self,
            message=message,
            actor=actor,
        )


class EscrowEvent(models.Model):
    """Immutable, append-only audit trail for an escrow transaction."""
    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escrow = models.ForeignKey(EscrowTransaction, on_delete=models.CASCADE, related_name='events')
    message    = models.TextField()
    actor      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Escrow Event'

    def __str__(self):
        return f'[{self.created_at:%d %b %Y %H:%M}] {self.message[:80]}'
