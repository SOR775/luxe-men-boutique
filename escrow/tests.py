from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model

from orders.models import Order
from payments.models import Payment
from escrow.models import EscrowTransaction
from escrow.tasks import auto_release_expired_escrows

User = get_user_model()


class EscrowTransactionTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer@example.com', username='buyer', password='pass1234'
        )
        self.staff = User.objects.create_superuser(
            email='admin@example.com', username='admin', password='pass1234'
        )

        self.order = Order.objects.create(
            user=self.buyer,
            shipping_name='John Buyer',
            shipping_phone='254700000001',
            shipping_email='buyer@example.com',
            shipping_address='123 Nairobi Lane',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            subtotal='100.00',
            shipping_cost='10.00',
            discount_amount='0.00',
            total='110.00',
        )

        self.payment = Payment.objects.create(
            order=self.order,
            method=Payment.Method.MPESA,
            status=Payment.Status.COMPLETED,
            amount=self.order.total,
            currency='KES',
            reference=self.order.order_number,
        )

    def test_escrow_created_when_payment_completes(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        self.assertEqual(escrow.status, EscrowTransaction.Status.FUNDED)
        self.assertEqual(escrow.amount, Decimal(self.order.total))
        self.assertEqual(escrow.buyer, self.buyer)
        self.assertIsNone(escrow.seller_shipped_at)

    def test_buyer_cannot_confirm_before_shipment(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        with self.assertRaises(ValueError):
            escrow.buyer_confirm(actor=self.buyer)

    def test_mark_shipped_then_buyer_confirm_requires_final_release(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        escrow.mark_shipped(tracking_number='TRK12345', courier='DHL', actor=self.staff)
        self.assertEqual(escrow.status, EscrowTransaction.Status.SHIPPED)
        self.assertIsNotNone(escrow.release_after)

        escrow.buyer_confirm(actor=self.buyer)
        escrow.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(escrow.status, EscrowTransaction.Status.DELIVERED)
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertIsNone(escrow.released_at)

        escrow.release_funds(actor=self.buyer)
        escrow.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(escrow.status, EscrowTransaction.Status.RELEASED)
        self.assertIsNotNone(escrow.released_at)
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

    def test_auto_release_releases_expired_escrow(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        escrow.mark_shipped(tracking_number='TRK12345', courier='DHL', actor=self.staff)
        escrow.release_after = timezone.now() - timedelta(hours=1)
        escrow.save(update_fields=['release_after'])

        released_count = auto_release_expired_escrows()
        escrow.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(released_count, 1)
        self.assertEqual(escrow.status, EscrowTransaction.Status.RELEASED)
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

    def test_open_dispute_and_refund_buyer(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        escrow.mark_shipped(tracking_number='TRK12345', courier='DHL', actor=self.staff)
        escrow.open_dispute(reason='Item not received', evidence='Tracking shows delay', actor=self.buyer)

        self.assertEqual(escrow.status, EscrowTransaction.Status.DISPUTED)
        self.assertEqual(escrow.dispute_reason, 'Item not received')

        escrow.refund_buyer(actor=self.staff, notes='Refund approved')
        escrow.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(escrow.status, EscrowTransaction.Status.REFUNDED)
        self.assertIsNotNone(escrow.refunded_at)
        self.assertEqual(self.order.status, Order.Status.REFUNDED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_admin_can_release_disputed_escrow(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        escrow.mark_shipped(tracking_number='TRK12345', courier='DHL', actor=self.staff)
        escrow.open_dispute(reason='Item damaged', actor=self.buyer)

        escrow.release_funds(actor=self.staff, notes='Seller appealed successful')
        escrow.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(escrow.status, EscrowTransaction.Status.RELEASED)
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

    def test_staff_can_run_auto_release_action(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        escrow.mark_shipped(tracking_number='TRK12345', courier='DHL', actor=self.staff)
        escrow.release_after = timezone.now() - timedelta(hours=1)
        escrow.save(update_fields=['release_after'])

        self.client.force_login(self.staff)
        response = self.client.post(reverse('escrow:auto_release'), follow=True)

        self.assertRedirects(response, reverse('escrow:dashboard'))
        self.assertContains(response, 'Auto-release complete')

        escrow.refresh_from_db()
        self.assertEqual(escrow.status, EscrowTransaction.Status.RELEASED)

    def test_staff_shipping_view_redirects_after_marking_shipped(self):
        escrow = EscrowTransaction.objects.get(payment=self.payment)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse('escrow:ship', kwargs={'escrow_id': escrow.id}),
            {'tracking_number': 'TRK12345', 'courier': 'DHL'},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('escrow:status', kwargs={'escrow_id': escrow.id}))
        escrow.refresh_from_db()
        self.assertEqual(escrow.status, EscrowTransaction.Status.SHIPPED)

    def test_admin_dashboard_search_filters_escrows(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('escrow:dashboard'), {'q': 'buyer@example.com'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Escrow Dashboard')
        self.assertContains(response, self.order.order_number)
