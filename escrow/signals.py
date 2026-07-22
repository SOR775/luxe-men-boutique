"""
escrow/signals.py
Automatically create an EscrowTransaction when a Payment is marked COMPLETED.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='payments.Payment')
def create_escrow_on_payment_complete(sender, instance, **kwargs):
    """When a payment completes, create or update the escrow record for the order."""
    from decimal import Decimal
    from django.db.models import Sum
    from payments.models import Payment
    from escrow.models import EscrowTransaction

    if instance.status != Payment.Status.COMPLETED:
        return

    order = instance.order
    buyer = order.user  # May be None for guest checkouts

    # Calculate total completed payments for this order
    paid_agg = Payment.objects.filter(order=order, status=Payment.Status.COMPLETED).aggregate(total=Sum('amount'))
    total_completed_paid = paid_agg.get('total') or Decimal('0')

    escrow = EscrowTransaction.objects.filter(order=order).first()

    if escrow:
        escrow.amount = total_completed_paid
        if not escrow.payment_id:
            escrow.payment = instance
        escrow.save(update_fields=['amount', 'payment', 'updated_at'])
        escrow._log(
            f'Escrow updated — total held {instance.currency} {total_completed_paid}. Payment method added: {instance.get_method_display()}.',
            actor=buyer,
        )
    else:
        escrow = EscrowTransaction.objects.create(
            order=order,
            payment=instance,
            buyer=buyer,
            amount=total_completed_paid,
            currency=instance.currency,
            status=EscrowTransaction.Status.FUNDED,
        )
        escrow._log(
            f'Escrow funded — {instance.currency} {total_completed_paid} held securely. Payment method: {instance.get_method_display()}.',
            actor=buyer,
        )
