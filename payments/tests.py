from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Order
from payments.models import Payment, MpesaTransaction
from wallets.models import WalletTopUp


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='payer@example.com',
            username='payeruser',
            password='StrongPass123!',
        )
        self.order = Order.objects.create(
            user=self.user,
            shipping_name='Test Buyer',
            shipping_phone='0712345678',
            shipping_email='payer@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            subtotal=Decimal('5000.00'),
            total=Decimal('5000.00'),
        )

    @patch('payments.views.mpesa_client.stk_push')
    def test_payment_retry_after_failed_or_pending_attempt(self, mock_stk_push):
        mock_stk_push.return_value = {
            'ResponseCode': '0',
            'MerchantRequestID': 'm-test-1',
            'CheckoutRequestID': 'c-test-1',
            'CustomerMessage': 'STK Push sent',
        }

        self.client.force_login(self.user)
        # Attempt 1
        resp1 = self.client.post(f'/payments/mpesa/push/{self.order.id}/', {'phone_number': '0712345678'})
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1['success'])

        # Order has an uncompleted Payment with status PENDING/PROCESSING.
        # Now initiate Attempt 2: it should NOT report "Order already paid".
        mock_stk_push.return_value = {
            'ResponseCode': '0',
            'MerchantRequestID': 'm-test-2',
            'CheckoutRequestID': 'c-test-2',
            'CustomerMessage': 'STK Push sent attempt 2',
        }
        resp2 = self.client.post(f'/payments/mpesa/push/{self.order.id}/', {'phone_number': '0712345678'})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2['success'])
        self.assertEqual(data2['checkout_request_id'], 'c-test-2')

    @patch('payments.views.mpesa_client.stk_query')
    def test_mpesa_query_handles_cancelled_or_failed_result_code(self, mock_stk_query):
        payment = Payment.objects.create(
            order=self.order,
            method=Payment.Method.MPESA,
            amount=Decimal('5000.00'),
            status=Payment.Status.PROCESSING,
        )
        txn = MpesaTransaction.objects.create(
            payment=payment,
            phone_number='254712345678',
            amount=Decimal('5000.00'),
            account_reference=self.order.order_number,
            checkout_request_id='c-cancel-123',
            status=MpesaTransaction.Status.PENDING,
        )

        # M-Pesa returns code 1032 (Request cancelled by user)
        mock_stk_query.return_value = {
            'ResultCode': '1032',
            'ResultDesc': 'Request cancelled by user',
        }

        resp = self.client.post(f'/payments/mpesa/query/{txn.checkout_request_id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'failed')

        txn.refresh_from_db()
        self.assertEqual(txn.status, MpesaTransaction.Status.FAILED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.UNPAID)

    @patch('payments.views.mpesa_client.stk_query')
    def test_mpesa_query_completes_wallet_topup(self, mock_stk_query):
        topup = WalletTopUp.objects.create(
            user=self.user,
            amount=Decimal('1500.00'),
            currency='KES',
            payment_method='mpesa',
            checkout_request_id='c-topup-999',
            status=WalletTopUp.Status.PENDING,
        )

        mock_stk_query.return_value = {
            'ResultCode': '0',
            'ResultDesc': 'Success',
        }

        resp = self.client.post(f'/payments/mpesa/query/{topup.checkout_request_id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')

        topup.refresh_from_db()
        self.assertEqual(topup.status, WalletTopUp.Status.COMPLETED)
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance, Decimal('1500.00'))
