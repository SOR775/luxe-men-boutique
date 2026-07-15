import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Order, ReturnRequest
from payments.models import Payment
from escrow.models import EscrowTransaction
from .models import Wallet, WalletTopUp


class WalletModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='wallet@example.com',
            username='walletuser',
            password='StrongPass123!',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_credit_and_debit_flow(self):
        self.wallet.credit(Decimal('100.00'), description='Top up', reference='topup-1')
        self.wallet.debit(Decimal('25.00'), description='Purchase', reference='purchase-1')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('75.00'))
        self.assertEqual(self.wallet.transactions.count(), 2)

    def test_debit_rejects_insufficient_funds(self):
        with self.assertRaises(ValueError):
            self.wallet.debit(Decimal('10.00'), description='Too much')

    def test_return_request_completion_creates_refund_credit(self):
        order = Order.objects.create(
            user=self.user,
            shipping_name='Test User',
            shipping_phone='0700000000',
            shipping_email='wallet@example.com',
            shipping_address='1 Example Road',
            shipping_city='Nairobi',
            subtotal=Decimal('120.00'),
            total=Decimal('120.00'),
        )
        refund_request = ReturnRequest.objects.create(
            order=order,
            user=self.user,
            type=ReturnRequest.Type.RETURN,
            reason='Not needed',
        )

        refund_request.complete(actor=self.user)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('120.00'))

    def test_wallet_topup_marks_completed_and_creates_credit(self):
        topup = WalletTopUp.objects.create(
            user=self.user,
            amount=Decimal('50.00'),
            currency='KES',
            payment_method='mpesa',
            payment_reference='TOPUP-1',
            status=WalletTopUp.Status.PENDING,
        )

        topup.mark_completed(actor=self.user)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('50.00'))

    def test_wallet_topup_get_redirects_to_overview(self):
        self.client.force_login(self.user)
        response = self.client.get('/wallet/top-up/', follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/wallet/')

    def test_wallet_can_pay_full_order_balance(self):
        self.wallet.credit(Decimal('100.00'), description='Seed', reference='seed-1')
        order = Order.objects.create(
            user=self.user,
            shipping_name='Test User',
            shipping_phone='0700000000',
            shipping_email='wallet@example.com',
            shipping_address='1 Example Road',
            shipping_city='Nairobi',
            subtotal=Decimal('80.00'),
            total=Decimal('80.00'),
        )

        self.client.force_login(self.user)
        response = self.client.post(f'/payments/wallet/{order.id}/')

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.ESCROW)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('20.00'))

    def test_wallet_can_pay_partial_order_and_leave_remaining_balance(self):
        self.wallet.credit(Decimal('40.00'), description='Seed', reference='seed-2')
        order = Order.objects.create(
            user=self.user,
            shipping_name='Test User',
            shipping_phone='0700000000',
            shipping_email='wallet@example.com',
            shipping_address='1 Example Road',
            shipping_city='Nairobi',
            subtotal=Decimal('80.00'),
            total=Decimal('80.00'),
        )

        self.client.force_login(self.user)
        response = self.client.post(f'/payments/wallet/{order.id}/')

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PARTIAL)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))
        self.assertTrue(Payment.objects.filter(order=order).exists())

    @patch('wallets.views.mpesa_client.stk_push')
    def test_wallet_topup_starts_stk_push_instead_of_immediate_credit(self, mock_stk_push):
        mock_stk_push.return_value = {
            'ResponseCode': '0',
            'ResponseDescription': 'Success',
            'CustomerMessage': 'Please complete the M-Pesa prompt',
            'MerchantRequestID': 'm-1',
            'CheckoutRequestID': 'c-1',
        }

        self.client.force_login(self.user)
        response = self.client.post('/wallet/top-up/', {'amount': '1000', 'phone_number': '0712345678'})

        self.assertEqual(response.status_code, 302)
        topup = WalletTopUp.objects.get(user=self.user)
        self.assertEqual(topup.status, WalletTopUp.Status.PENDING)
        self.assertEqual(topup.checkout_request_id, 'c-1')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    def test_successful_mpesa_callback_credits_wallet_topup(self):
        topup = WalletTopUp.objects.create(
            user=self.user,
            amount=Decimal('50.00'),
            currency='KES',
            payment_method='mpesa',
            payment_reference='TOPUP-2',
            checkout_request_id='c-2',
            status=WalletTopUp.Status.PENDING,
        )

        callback_payload = {
            'Body': {
                'stkCallback': {
                    'ResultCode': '0',
                    'ResultDesc': 'The service request is processed successfully',
                    'CheckoutRequestID': 'c-2',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'MpesaReceiptNumber', 'Value': 'RCPT-001'},
                            {'Name': 'PhoneNumber', 'Value': '254712345678'},
                            {'Name': 'Amount', 'Value': 50},
                            {'Name': 'TransactionDate', 'Value': '20260711123030'},
                        ]
                    },
                }
            }
        }

        response = self.client.post(
            '/payments/mpesa/callback/',
            data=json.dumps(callback_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        topup.refresh_from_db()
        self.assertEqual(topup.status, WalletTopUp.Status.COMPLETED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('50.00'))

    def test_staff_can_credit_wallet_from_management_page(self):
        staff_user = get_user_model().objects.create_user(
            email='staff@example.com',
            username='staffuser',
            password='StrongPass123!',
            is_staff=True,
        )

        self.client.force_login(staff_user)
        response = self.client.post(
            '/wallet/manage/',
            {
                'user': self.user.id,
                'action': 'credit',
                'amount': '125.00',
                'description': 'Manual adjustment',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('125.00'))
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_admin_wallet_transaction_changelist_renders(self):
        admin_user = get_user_model().objects.create_superuser(
            email='admin@example.com',
            username='adminuser',
            password='StrongPass123!',
        )

        self.client.force_login(admin_user)
        response = self.client.get('/admin/wallets/wallettransaction/')

        self.assertEqual(response.status_code, 200)

    def test_referral_bonus_creates_wallet_credit(self):
        self.user.award_referral_bonus(amount=Decimal('25.00'), reference='ref-1')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('25.00'))

    def test_transactions_reconcile_with_balance(self):
        # seed multiple transactions and validate reconciliation
        self.wallet.credit(Decimal('200.00'), description='Seed A', reference='seed-a')
        self.wallet.debit(Decimal('50.00'), description='Purchase A', reference='p-a')
        self.wallet.credit(Decimal('30.00'), description='Seed B', reference='seed-b')
        self.wallet.debit(Decimal('10.00'), description='Purchase B', reference='p-b')

        self.wallet.refresh_from_db()
        expected, actual, discrepancy = self.wallet.reconcile()
        self.assertEqual(expected, actual)
        self.assertEqual(discrepancy, Decimal('0'))

    def test_concurrent_debits_no_negative_balance(self):
        # seed wallet with 100
        self.wallet.credit(Decimal('100.00'), description='Seed concurrent', reference='seed-conc')

        results = []

        def attempt_debit(amount, out_list):
            try:
                self.wallet.debit(amount, description='concurrent purchase', reference='conc', actor=self.user)
                out_list.append('ok')
            except Exception as e:
                out_list.append(str(e))

        import threading

        t1 = threading.Thread(target=attempt_debit, args=(Decimal('60.00'), results))
        t2 = threading.Thread(target=attempt_debit, args=(Decimal('60.00'), results))

        t1.start(); t2.start()
        t1.join(); t2.join()

        # Exactly one should succeed and one should fail due to insufficient funds
        self.assertIn('ok', results)
        self.assertTrue(any('Insufficient' in r for r in results if r != 'ok'))

        self.wallet.refresh_from_db()
        # Balance should be 40 if one debit succeeded
        self.assertEqual(self.wallet.balance, Decimal('40.00'))
