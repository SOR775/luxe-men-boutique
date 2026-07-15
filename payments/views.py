"""
payments/views.py — Payment Selection, M-Pesa STK Push, Callback, Status
"""
import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import View
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.db.models import Sum

from orders.models import Order, OrderEvent
from notifications.models import Notification
from wallets.models import Wallet, WalletTopUp
from .models import Payment, MpesaTransaction, MpesaWebhookLog
from .mpesa import mpesa_client

logger = logging.getLogger(__name__)


def notify_admins_payment_complete(order):
    """Notify all active staff users that a customer payment has completed."""
    User = get_user_model()
    admin_url = reverse('orders:admin_orders')
    for admin in User.objects.filter(is_active=True, is_staff=True):
        try:
            Notification.create(
                user=admin,
                title=f'Payment received for order #{order.order_number}',
                message=(
                    f'Payment has been confirmed for order {order.order_number}. '
                    'Please review and progress it to shipping or escrow release.'
                ),
                target_url=admin_url,
                level=Notification.Level.INFO,
            )
        except Exception:
            continue


# ─── Payment Method Selection ─────────────────────────────────────────────────

class PaymentSelectView(View):
    template_name = 'payments/select.html'

    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        # Compute remaining due after any existing successful/pending payments
        paid_agg = Payment.objects.filter(order=order).exclude(status=Payment.Status.FAILED).aggregate(total_paid=Sum('amount'))
        paid = paid_agg.get('total_paid') or Decimal('0')
        amount_to_pay = max(order.total - paid, Decimal('0'))

        context = {'order': order, 'amount_to_pay': amount_to_pay}

        if request.user.is_authenticated and order.user_id == request.user.id:
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            wallet_balance = wallet.balance
            # compute coverage against remaining amount, not original total
            wallet_coverage = min(wallet_balance, amount_to_pay)
            wallet_remaining = max(amount_to_pay - wallet_balance, Decimal('0'))
            context.update({
                'wallet_balance': wallet_balance,
                'wallet_currency': wallet.currency,
                'wallet_coverage': wallet_coverage,
                'wallet_remaining': wallet_remaining,
            })

        return render(request, self.template_name, context)


class WalletPaymentView(LoginRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        if order.user_id != request.user.id:
            messages.error(request, 'You can only pay your own orders with your wallet.')
            return redirect('payments:select', order_id=order.id)


        # Compute remaining due after any existing successful/pending payments
        paid_agg = Payment.objects.filter(order=order).exclude(status=Payment.Status.FAILED).aggregate(total_paid=Sum('amount'))
        paid = paid_agg.get('total_paid') or Decimal('0')
        remaining = max(order.total - paid, Decimal('0'))

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        available_amount = wallet.balance
        amount_to_use = min(available_amount, remaining)

        if amount_to_use <= 0:
            messages.error(request, 'Your wallet balance is empty or there is no remaining balance to pay.')
            return redirect('payments:select', order_id=order.id)

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            amount_to_use = min(wallet.balance, remaining)
            if amount_to_use <= 0:
                messages.error(request, 'Your wallet balance is empty or there is no remaining balance to pay.')
                return redirect('payments:select', order_id=order.id)

            wallet.debit(
                amount_to_use,
                description=f'Payment for order {order.order_number}',
                reference=f'order-{order.order_number}',
                actor=request.user,
                order=order,
            )

            # If the wallet covers the full total, mark payment completed and let escrow signal run.
            # For partial wallet use, create a pending payment record so escrow is NOT created.
            payment_status = Payment.Status.COMPLETED if amount_to_use >= remaining else Payment.Status.PENDING

            payment = Payment.objects.create(
                order=order,
                method=Payment.Method.WALLET,
                amount=amount_to_use,
                currency='KES',
                reference=f'wallet-{order.order_number}',
                description='Wallet payment',
                status=payment_status,
            )

            if amount_to_use >= remaining:
                order.payment_status = Order.PaymentStatus.PAID
                order.status = Order.Status.ESCROW
                message = f'Your wallet covered the remaining balance. Order #{order.order_number} is now in escrow.'
            else:
                order.payment_status = Order.PaymentStatus.PARTIAL
                # Do not create escrow for partial payments — keep order pending until remaining payment
                order.status = Order.Status.PENDING
                message = (
                    f'Your wallet covered KES {amount_to_use:.2f}. '
                    f'Remaining balance KES {remaining - amount_to_use:.2f} is still due.'
                )

            order.save(update_fields=['payment_status', 'status', 'updated_at'])
            OrderEvent.objects.create(
                order=order,
                message=message,
                created_by=request.user,
            )

        messages.success(request, message)
        return redirect('payments:select', order_id=order.id)


# ─── M-Pesa STK Push ─────────────────────────────────────────────────────────

class MpesaSTKPushView(View):
    """Initiate STK Push and create pending payment records."""

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        phone_number = request.POST.get('phone_number', '').strip().replace(' ', '').replace('-', '')

        # Normalize to 254XXXXXXXXX
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]

        if not phone_number or len(phone_number) != 12 or not phone_number.startswith('254'):
            return JsonResponse({'success': False, 'error': 'Invalid M-Pesa phone number.'})

        # Compute remaining balance after any existing successful/pending payments
        paid_agg = Payment.objects.filter(order=order).exclude(status=Payment.Status.FAILED).aggregate(total_paid=Sum('amount'))
        paid = paid_agg.get('total_paid') or Decimal('0')
        remaining = order.total - paid

        if remaining <= 0:
            return JsonResponse({'success': False, 'error': 'Order already paid or no remaining balance.'})

        # Create a Payment record for the remaining amount
        payment = Payment.objects.create(
            order=order,
            method=Payment.Method.MPESA,
            amount=remaining,
            reference=f"{order.order_number}-mpesa",
        )

        # Initiate STK Push for the remaining amount
        response = mpesa_client.stk_push(
            phone_number=phone_number,
            amount=int(remaining),
            account_reference=order.order_number,
            transaction_desc=f"Order {order.order_number}",
        )

        if 'error' in response or response.get('ResponseCode') != '0':
            payment.status = Payment.Status.FAILED
            payment.save()
            error_msg = response.get('error') or response.get('ResponseDescription', 'STK Push failed.')
            return JsonResponse({'success': False, 'error': error_msg})

        # Record M-Pesa transaction
        MpesaTransaction.objects.create(
            payment=payment,
            phone_number=phone_number,
            amount=remaining,
            account_reference=order.order_number,
            transaction_desc=f"Order {order.order_number}",
            merchant_request_id=response.get('MerchantRequestID', ''),
            checkout_request_id=response.get('CheckoutRequestID', ''),
            response_code=response.get('ResponseCode', ''),
            response_description=response.get('ResponseDescription', ''),
            customer_message=response.get('CustomerMessage', ''),
            status=MpesaTransaction.Status.PENDING,
        )

        payment.status = Payment.Status.PROCESSING
        payment.save()

        return JsonResponse({
            'success': True,
            'message': response.get('CustomerMessage', 'STK Push sent. Check your phone.'),
            'checkout_request_id': response.get('CheckoutRequestID'),
            'order_id': str(order.id),
        })


# ─── STK Push Query (Polling) ─────────────────────────────────────────────────

class MpesaQueryView(View):
    """Poll M-Pesa for STK Push status."""

    def post(self, request, checkout_request_id):
        txn = get_object_or_404(MpesaTransaction, checkout_request_id=checkout_request_id)

        # If already resolved, return cached status
        if txn.is_complete:
            return JsonResponse({'status': 'success', 'receipt': txn.mpesa_receipt_number})
        if txn.is_failed:
            return JsonResponse({'status': 'failed', 'message': txn.result_description})

        result = mpesa_client.stk_query(checkout_request_id)
        result_code = str(result.get('ResultCode', ''))

        if result_code == '0':
            txn.status = MpesaTransaction.Status.SUCCESS
            txn.result_code = result_code
            txn.result_description = result.get('ResultDesc', '')
            txn.save()
            # Mark payment as complete — triggers escrow creation via signal
            txn.payment.status = Payment.Status.COMPLETED
            txn.payment.save()
            order = txn.payment.order
            order.payment_status = Order.PaymentStatus.PAID
            order.status = Order.Status.ESCROW  # Funds now held in escrow
            order.save()
            try:
                if order.user_id:
                    Notification.create(
                        user=order.user,
                        title=f'Payment confirmed for order #{order.order_number}',
                        message='Your payment is complete and the order has entered escrow.',
                        target_url=f'/cart/history/{order.order_number}/',
                        level=Notification.Level.SUCCESS,
                        send_sms=True,
                    )
            except Exception:
                pass
            try:
                notify_admins_payment_complete(order)
            except Exception:
                pass

        return JsonResponse({'status': 'success'})


# ─── Daraja Callback (Webhook) ─────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class MpesaCallbackView(View):
    """
    Receives the asynchronous M-Pesa STK Push result from Safaricom.
    This URL must be HTTPS and publicly accessible.
    """

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("[M-Pesa Callback] Invalid JSON body received")
            return HttpResponse(status=400)

        # Log raw webhook
        webhook_log = MpesaWebhookLog.objects.create(
            url=request.build_absolute_uri(),
            headers=dict(request.headers),
            body=body,
            ip_address=self._get_client_ip(request),
        )

        parsed = mpesa_client.process_callback(body)
        checkout_request_id = parsed.get('checkout_request_id')

        if not checkout_request_id:
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})

        try:
            with transaction.atomic():
                wallet_topup = WalletTopUp.objects.select_for_update().filter(
                    checkout_request_id=checkout_request_id
                ).first()

                if wallet_topup is not None:
                    if parsed.get('result_code') == '0':
                        wallet_topup.mark_completed(actor=wallet_topup.user)
                    else:
                        wallet_topup.status = WalletTopUp.Status.FAILED
                        wallet_topup.save(update_fields=['status', 'updated_at'])
                else:
                    txn = MpesaTransaction.objects.select_for_update().get(
                        checkout_request_id=checkout_request_id
                    )
                    txn.result_code        = parsed.get('result_code', '')
                    txn.result_description = parsed.get('result_desc', '')
                    txn.callback_raw       = body

                    if parsed.get('result_code') == '0':
                        txn.mpesa_receipt_number = parsed.get('receipt', '')
                        txn.transaction_date     = parsed.get('date', '')
                        txn.status               = MpesaTransaction.Status.SUCCESS
                        # Update payment and order — escrow is created via signal
                        txn.payment.status = Payment.Status.COMPLETED
                        txn.payment.save()
                        order = txn.payment.order
                        order.payment_status = Order.PaymentStatus.PAID
                        order.status = Order.Status.ESCROW  # Funds held in escrow
                        order.save()
                        from orders.models import OrderEvent
                        OrderEvent.objects.create(
                            order=order,
                            message=f"Payment confirmed via M-Pesa. Receipt: {txn.mpesa_receipt_number}. Funds held in escrow.",
                        )
                        try:
                            notify_admins_payment_complete(order)
                        except Exception:
                            pass
                    else:
                        txn.status = MpesaTransaction.Status.FAILED
                        txn.payment.status = Payment.Status.FAILED
                        txn.payment.save()

                    txn.save()

                # Mark webhook as processed
                webhook_log.processed = True
                webhook_log.save(update_fields=['processed'])

        except MpesaTransaction.DoesNotExist:
            logger.warning(f"[M-Pesa Callback] No transaction for CheckoutRequestID: {checkout_request_id}")

        # Always return 200 to acknowledge Safaricom
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})

    @staticmethod
    def _get_client_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


# ─── Payment Success / Failure Pages ─────────────────────────────────────────

class PaymentSuccessView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        escrow = getattr(order, 'escrow', None)
        return render(request, 'payments/success.html', {'order': order, 'escrow': escrow})


class PaymentFailedView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        return render(request, 'payments/failed.html', {'order': order})
