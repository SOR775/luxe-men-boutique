"""
escrow/signals.py
Automatically create an EscrowTransaction when a Payment is marked COMPLETED.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='payments.Payment')
def create_escrow_on_payment_complete(sender, instance, **kwargs):
    """When a payment completes, create (or retrieve) the escrow record."""
    from payments.models import Payment
    from escrow.models import EscrowTransaction

    if instance.status != Payment.Status.COMPLETED:
        return

    # Avoid duplicate escrow records
    if EscrowTransaction.objects.filter(payment=instance).exists():
        return

    order = instance.order
    buyer = order.user  # May be None for guest checkouts

    escrow = EscrowTransaction.objects.create(
        order=order,
        payment=instance,
        buyer=buyer,
        amount=instance.amount,
        currency=instance.currency,
        status=EscrowTransaction.Status.FUNDED,
    )
    escrow._log(
        f'Escrow funded — {instance.currency} {instance.amount} held securely. '
        f'Payment method: {instance.get_method_display()}.',
        actor=buyer,
    )
