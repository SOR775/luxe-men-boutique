# One-off reconciliation script: mark orders PAID where payments cover total
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

from orders.models import Order
from payments.models import Payment

fixed = []
with transaction.atomic():
    qs = Order.objects.filter(payment_status__in=(Order.PaymentStatus.UNPAID, Order.PaymentStatus.PARTIAL))
    for o in qs:
        paid_agg = Payment.objects.filter(order=o).exclude(status=Payment.Status.FAILED).aggregate(total_paid=Sum('amount'))
        paid = paid_agg.get('total_paid') or Decimal('0')
        if paid >= o.total:
            # Ensure a completed payment exists so escrow signal can run
            if not Payment.objects.filter(order=o, status=Payment.Status.COMPLETED).exists():
                p = Payment.objects.filter(order=o).order_by('-created_at').first()
                if p:
                    p.status = Payment.Status.COMPLETED
                    p.save()
            o.payment_status = Order.PaymentStatus.PAID
            o.status = Order.Status.ESCROW
            o.save(update_fields=['payment_status', 'status', 'updated_at'])
            fixed.append((str(o.order_number), str(p.id) if p else 'no-payment'))

print('Reconciled orders:', fixed)
