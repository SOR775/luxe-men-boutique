from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from payments.mpesa import mpesa_client
from .models import Wallet, WalletTopUp


class WalletOverviewView(LoginRequiredMixin, TemplateView):
    template_name = 'wallets/overview.html'

    def dispatch(self, request, *args, **kwargs):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        request.wallet = wallet
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = getattr(self.request, 'wallet', None)
        context['wallet'] = wallet
        context['recent_transactions'] = wallet.transactions.all()[:5] if wallet else []
        return context


class WalletTransactionsView(LoginRequiredMixin, TemplateView):
    template_name = 'wallets/transactions.html'

    def dispatch(self, request, *args, **kwargs):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        request.wallet = wallet
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = getattr(self.request, 'wallet', None)
        context['wallet'] = wallet
        context['transactions'] = wallet.transactions.all() if wallet else []
        return context


class WalletManagementView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'wallets/manage.html'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        User = get_user_model()
        context['users'] = User.objects.order_by('email', 'username')
        context['wallets'] = Wallet.objects.select_related('user').order_by('-balance', 'user__email')
        context['pending_topups'] = WalletTopUp.objects.filter(status=WalletTopUp.Status.PENDING).select_related('user')[:10]
        return context

    def post(self, request, *args, **kwargs):
        user_id = request.POST.get('user', '').strip()
        action = request.POST.get('action', 'credit').strip()
        amount_value = request.POST.get('amount', '').strip()
        description = request.POST.get('description', '').strip()

        try:
            amount = Decimal(amount_value)
        except Exception:
            messages.error(request, 'Please enter a valid amount.')
            return redirect('wallets:manage')

        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('wallets:manage')

        if not user_id:
            messages.error(request, 'Select a user to manage.')
            return redirect('wallets:manage')

        User = get_user_model()
        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, 'That user could not be found.')
            return redirect('wallets:manage')

        wallet, _ = Wallet.objects.get_or_create(user=target_user)
        try:
            if action == 'debit':
                wallet.debit(amount, description=description or 'Manual wallet adjustment', reference='manual-adjustment', actor=request.user)
                messages.success(request, f'Wallet debited for {target_user.email or target_user.username}.')
            else:
                wallet.credit(amount, description=description or 'Manual wallet adjustment', reference='manual-adjustment', actor=request.user)
                messages.success(request, f'Wallet credited for {target_user.email or target_user.username}.')
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('wallets:manage')

        return redirect('wallets:manage')


class WalletTopUpView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect('wallets:overview')

    def post(self, request, *args, **kwargs):
        amount_value = request.POST.get('amount', '').strip()
        phone_number = request.POST.get('phone_number', '').strip().replace(' ', '').replace('-', '')
        try:
            amount = Decimal(amount_value)
        except Exception:
            messages.error(request, 'Please enter a valid amount.')
            return redirect('wallets:overview')

        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('wallets:overview')

        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]

        if not phone_number or len(phone_number) != 12 or not phone_number.startswith('254'):
            messages.error(request, 'Enter a valid Safaricom phone number to receive the STK push.')
            return redirect('wallets:overview')

        top_up = WalletTopUp.objects.create(
            user=request.user,
            amount=amount,
            currency='KES',
            payment_method='mpesa',
            payment_reference=f'topup-{request.user.id}-{amount}',
            phone_number=phone_number,
            description='Wallet top-up',
            status=WalletTopUp.Status.PENDING,
        )

        response = mpesa_client.stk_push(
            phone_number=phone_number,
            amount=int(amount),
            account_reference=f'WAL-{request.user.id}',
            transaction_desc='Wallet Top-up',
        )

        if 'error' in response or response.get('ResponseCode') != '0':
            top_up.status = WalletTopUp.Status.FAILED
            top_up.save(update_fields=['status', 'updated_at'])
            messages.error(request, response.get('error') or response.get('ResponseDescription', 'Could not start M-Pesa STK push.'))
            return redirect('wallets:overview')

        top_up.checkout_request_id = response.get('CheckoutRequestID', '')
        top_up.save(update_fields=['checkout_request_id', 'updated_at'])
        messages.success(request, 'An M-Pesa STK push has been sent to your phone. Complete the prompt to top up your wallet.')
        return redirect('wallets:overview')
