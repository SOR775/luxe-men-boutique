"""
escrow/views.py — Escrow Status, Actions & Admin Dashboard
"""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse, Http404
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from notifications.models import Notification
from .models import EscrowTransaction

logger = logging.getLogger(__name__)


def _send_escrow_email(subject, body, recipient_list):
    """Fire-and-forget escrow notification email."""
    try:
        send_mail(
            subject=f'[{getattr(settings, "SITE_NAME", "LUXE MEN")}] {subject}',
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@luxemen.co.ke'),
            recipient_list=recipient_list,
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning(f'[Escrow email] Failed: {exc}')


# ─── Buyer / Seller: Escrow Status Page ──────────────────────────────────────

class EscrowStatusView(LoginRequiredMixin, View):
    """
    Main escrow status page — visible to the buyer and staff.
    Shows the full timeline and available actions.
    """
    template_name = 'escrow/status.html'

    def get(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        # Only buyer or staff can view
        if not request.user.is_staff and escrow.buyer != request.user:
            raise Http404
        events = escrow.events.all()
        return render(request, self.template_name, {
            'escrow': escrow,
            'events': events,
        })


# ─── Admin / Staff: Mark as Shipped ──────────────────────────────────────────

@method_decorator(staff_member_required, name='dispatch')
class SellerMarkShippedView(View):
    """Admin marks the order as dispatched and enters tracking details."""

    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        tracking = request.POST.get('tracking_number', '').strip()
        courier  = request.POST.get('courier', '').strip()

        try:
            escrow.mark_shipped(tracking_number=tracking, courier=courier, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('escrow:status', escrow_id=escrow_id)

        messages.success(
            request,
            f'Order #{escrow.order.order_number} marked as shipped. '
            f'Auto-release in {escrow.AUTO_RELEASE_DAYS} days if buyer does not confirm.'
        )

        # Notify buyer
        if escrow.buyer and escrow.buyer.email:
            _send_escrow_email(
                subject=f'Your order #{escrow.order.order_number} has been shipped!',
                body=f"""Hi {escrow.buyer.get_short_name()},

Great news — your order #{escrow.order.order_number} has been dispatched!

Courier: {courier or 'N/A'}
Tracking: {tracking or 'N/A'}

Once you receive your items, please log in and confirm receipt. That confirmation will mark the order delivered, and you will then make a final release confirmation to complete the transaction.

If you do not confirm within {escrow.AUTO_RELEASE_DAYS} days, funds will be automatically released.

View your escrow: {settings.SITE_URL}/escrow/{escrow_id}/

Thank you,
{getattr(settings, 'SITE_NAME', 'LUXE MEN')}""",
                recipient_list=[escrow.buyer.email],
            )

            try:
                Notification.create(
                    user=escrow.buyer,
                    title=f'Order #{escrow.order.order_number} shipped',
                    message='Your order has left the warehouse. Track it in your escrow dashboard.',
                    target_url=f'/escrow/{escrow_id}/',
                    level=Notification.Level.INFO,
                    send_sms=True,
                )
            except Exception:
                pass

        return redirect('escrow:status', escrow_id=escrow_id)


# ─── Buyer: Confirm Receipt ───────────────────────────────────────────────────

class BuyerConfirmReceiptView(LoginRequiredMixin, View):
    """Buyer confirms they received the goods and then approves final fund release."""

    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)

        if escrow.buyer != request.user:
            messages.error(request, 'You are not the buyer for this escrow.')
            return redirect('core:home')

        try:
            if escrow.status == EscrowTransaction.Status.SHIPPED:
                escrow.buyer_confirm(actor=request.user)
                messages.success(
                    request,
                    '✅ Receipt confirmed. Your order is now marked delivered. Please confirm release to complete the transaction.'
                )
                try:
                    Notification.create(
                        user=request.user,
                        title=f'Order #{escrow.order.order_number} delivered',
                        message='Delivery confirmed. Your order is now marked delivered and awaits final release.',
                        target_url=f'/escrow/{escrow_id}/',
                        level=Notification.Level.SUCCESS,
                        send_sms=True,
                    )
                except Exception:
                    pass
                _send_escrow_email(
                    subject=f'Order #{escrow.order.order_number} marked delivered',
                    body=(
                        f'The buyer has confirmed delivery for order #{escrow.order.order_number}.\n'
                        f'The order is now marked delivered and awaits final release approval.\n\n'
                        f'Thank you!'
                    ),
                    recipient_list=[settings.DEFAULT_FROM_EMAIL],
                )
            elif escrow.status == EscrowTransaction.Status.DELIVERED:
                escrow.release_funds(actor=request.user)
                messages.success(
                    request,
                    '✅ Final confirmation complete. Funds have been released to the seller and the order is now completed.'
                )
                try:
                    Notification.create(
                        user=request.user,
                        title=f'Order #{escrow.order.order_number} completed',
                        message='Funds have been released and your order is now complete. Thank you for shopping with us.',
                        target_url=f'/escrow/{escrow_id}/',
                        level=Notification.Level.SUCCESS,
                        send_sms=True,
                    )
                except Exception:
                    pass
                _send_escrow_email(
                    subject=f'Funds released for order #{escrow.order.order_number}',
                    body=(
                        f'The buyer has completed final delivery confirmation for order #{escrow.order.order_number}.\n'
                        f'Escrow of {escrow.currency} {escrow.amount} has been released to the seller.\n\n'
                        f'Thank you!'
                    ),
                    recipient_list=[settings.DEFAULT_FROM_EMAIL],
                )
            else:
                raise ValueError('Escrow cannot be confirmed at this stage.')
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('escrow:status', escrow_id=escrow_id)

        return redirect('escrow:status', escrow_id=escrow_id)


# ─── Buyer: Open Dispute ──────────────────────────────────────────────────────

class BuyerOpenDisputeView(LoginRequiredMixin, View):
    """Buyer opens a dispute — pauses auto-release and alerts admin."""
    template_name = 'escrow/dispute_form.html'

    def get(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        if escrow.buyer != request.user:
            raise Http404
        return render(request, self.template_name, {'escrow': escrow})

    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)

        if escrow.buyer != request.user:
            messages.error(request, 'You are not the buyer for this escrow.')
            return redirect('core:home')

        reason_type = request.POST.get('reason_type', '').strip()
        reason = request.POST.get('reason', '').strip() or reason_type
        evidence = request.POST.get('evidence', '').strip()

        if not reason:
            messages.error(request, 'Please provide a reason for the dispute.')
            return render(request, self.template_name, {'escrow': escrow})

        try:
            escrow.open_dispute(reason=reason, evidence=evidence, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('escrow:status', escrow_id=escrow_id)

        messages.warning(
            request,
            '⚠️ Dispute submitted. Our team will review your case within 24–48 hours. '
            'Funds are held securely until resolved.'
        )

        # Alert admin
        _send_escrow_email(
            subject=f'🚨 Dispute opened on Order #{escrow.order.order_number}',
            body=(
                f'A buyer has opened a dispute.\n\n'
                f'Order: #{escrow.order.order_number}\n'
                f'Buyer: {request.user.email}\n'
                f'Amount: {escrow.currency} {escrow.amount}\n\n'
                f'Reason:\n{reason}\n\n'
                f'Evidence:\n{evidence or "None provided"}\n\n'
                f'Admin dashboard: {settings.SITE_URL}/escrow/dashboard/'
            ),
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
        )

        return redirect('escrow:status', escrow_id=escrow_id)


# ─── Admin: Resolve Dispute ───────────────────────────────────────────────────

@method_decorator(staff_member_required, name='dispatch')
class AdminResolveDisputeView(View):
    """Admin reviews the dispute and either releases funds or refunds the buyer."""
    template_name = 'escrow/resolve_dispute.html'

    def get(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id, status=EscrowTransaction.Status.DISPUTED)
        return render(request, self.template_name, {'escrow': escrow})

    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        decision = request.POST.get('decision')  # 'release' or 'refund'
        notes    = request.POST.get('notes', '').strip()

        try:
            if decision == 'release':
                escrow.release_funds(actor=request.user, notes=notes)
                messages.success(
                    request,
                    f'✅ Dispute resolved: funds of {escrow.currency} {escrow.amount} released to seller.'
                )
                self._notify_resolution(escrow, 'in the seller\'s favour — funds released to seller.')
            elif decision == 'refund':
                escrow.refund_buyer(actor=request.user, notes=notes)
                messages.success(
                    request,
                    f'🔄 Dispute resolved: {escrow.currency} {escrow.amount} refunded to buyer.'
                )
                self._notify_resolution(escrow, 'in the buyer\'s favour — refund initiated.')
            else:
                messages.error(request, 'Invalid decision. Choose "release" or "refund".')
                return render(request, self.template_name, {'escrow': escrow})
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect('escrow:dashboard')

    def _notify_resolution(self, escrow, outcome_text):
        if escrow.buyer and escrow.buyer.email:
            _send_escrow_email(
                subject=f'Dispute resolved — Order #{escrow.order.order_number}',
                body=(
                    f'Hi {escrow.buyer.get_short_name()},\n\n'
                    f'Your dispute for Order #{escrow.order.order_number} has been reviewed '
                    f'and resolved {outcome_text}\n\n'
                    f'Resolution notes: {escrow.admin_resolution_notes or "N/A"}\n\n'
                    f'Thank you for shopping with us.\n{getattr(settings, "SITE_NAME", "LUXE MEN")}'
                ),
                recipient_list=[escrow.buyer.email],
            )


# ─── Admin: Release Escrow ───────────────────────────────────────────────────

@method_decorator(staff_member_required, name='dispatch')
class AdminReleaseEscrowView(View):
    """Staff releases escrow funds from the dashboard."""

    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        try:
            escrow.release_funds(actor=request.user, notes='Admin release from dashboard.')
            messages.success(
                request,
                f'✅ Funds released to seller for order #{escrow.order.order_number}.'
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('escrow:dashboard')


# ─── Admin: Escrow Dashboard ──────────────────────────────────────────────────

@method_decorator(staff_member_required, name='dispatch')
class EscrowAdminDashboardView(TemplateView):
    """Overview of all escrow transactions for staff."""
    template_name = 'escrow/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get('q', '').strip()
        base_qs = EscrowTransaction.objects.all().select_related('order', 'buyer')

        if q:
            base_qs = base_qs.filter(
                Q(order__order_number__icontains=q)
                | Q(buyer__email__icontains=q)
                | Q(tracking_number__icontains=q)
                | Q(id__icontains=q)
            )
        ctx['search_term'] = q
        ctx['funded']    = base_qs.filter(status='funded')
        ctx['shipped']   = base_qs.filter(status='shipped')
        ctx['disputed']  = base_qs.filter(status='disputed')
        ctx['delivered'] = base_qs.filter(status='delivered')
        ctx['released']  = base_qs.filter(status='released')[:20]
        ctx['refunded']  = base_qs.filter(status='refunded')[:20]
        total_held = base_qs.filter(status__in=['funded', 'shipped', 'delivered', 'disputed']).aggregate(total=Sum('amount'))['total']
        ctx['total_held'] = total_held or 0
        ctx['status_cards'] = [
            ('Funded', base_qs.filter(status='funded').count(), '#3B82F6'),
            ('Shipped', base_qs.filter(status='shipped').count(), '#F59E0B'),
            ('Delivered', base_qs.filter(status='delivered').count(), '#10B981'),
            ('Disputed', base_qs.filter(status='disputed').count(), '#EF4444'),
            ('Released', base_qs.filter(status='released').count(), '#6B7280'),
            ('Refunded', base_qs.filter(status='refunded').count(), '#8B5CF6'),
        ]
        ctx['overdue'] = [e for e in ctx['shipped'] if e.is_auto_releasable]
        return ctx


@method_decorator(staff_member_required, name='dispatch')
class EscrowAutoReleaseView(View):
    """Staff action to manually run escrow auto-release from the dashboard."""

    def post(self, request):
        from .tasks import auto_release_expired_escrows

        released = auto_release_expired_escrows()
        messages.success(request, f'Auto-release complete: {released} escrow(s) released.')
        return redirect('escrow:dashboard')


# ─── AJAX: Quick Status Check ─────────────────────────────────────────────────

class EscrowStatusAPIView(LoginRequiredMixin, View):
    """JSON endpoint for polling escrow status (used by frontend)."""

    def get(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, pk=escrow_id)
        if not request.user.is_staff and escrow.buyer != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return JsonResponse({
            'status': escrow.status,
            'status_display': escrow.get_status_display(),
            'days_until_auto_release': escrow.days_until_auto_release,
            'tracking_number': escrow.tracking_number,
            'courier': escrow.courier,
            'amount': str(escrow.amount),
            'currency': escrow.currency,
        })


# ─── Seller: Sales Dashboard ──────────────────────────────────────────────────

class SellerSalesDashboardView(LoginRequiredMixin, TemplateView):
    """Seller dashboard showing all their sales with earnings tracking."""
    template_name = 'escrow/seller_dashboard.html'

    def get_context_data(self, **kwargs):
        from django.db.models import Q, Sum, Count, F
        from orders.models import Order
        from wallets.models import Wallet, WalletTransaction

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get user's wallet
        wallet, _ = Wallet.objects.get_or_create(user=user)
        ctx['wallet'] = wallet

        # Get all orders where user is the seller
        orders = Order.objects.filter(seller=user).select_related('user', 'escrow__payment').prefetch_related('items')
        
        # Status breakdown
        ctx['total_orders'] = orders.count()
        ctx['pending_orders'] = orders.filter(status__in=['pending', 'paid', 'packing']).count()
        ctx['shipped_orders'] = orders.filter(status='shipped').count()
        ctx['completed_orders'] = orders.filter(status='completed').count()
        
        # Financial summary
        total_sales = orders.aggregate(total=Sum('total'))['total'] or 0
        ctx['total_sales'] = total_sales
        ctx['wallet_balance'] = wallet.balance
        
        # Recent transactions (wallet credits from escrow releases)
        ctx['recent_credits'] = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='credit'
        ).order_by('-created_at')[:10]
        
        # Released escrows (completed sales with funds paid)
        released_escrows = EscrowTransaction.objects.filter(
            order__seller=user,
            status=EscrowTransaction.Status.RELEASED
        ).select_related('order', 'buyer').order_by('-released_at')[:20]
        ctx['released_escrows'] = released_escrows
        
        # Pending escrows (awaiting action)
        pending_escrows = EscrowTransaction.objects.filter(
            order__seller=user,
            status__in=[
                EscrowTransaction.Status.FUNDED,
                EscrowTransaction.Status.SHIPPED,
                EscrowTransaction.Status.DELIVERED,
            ]
        ).select_related('order', 'buyer').order_by('-created_at')
        ctx['pending_escrows'] = pending_escrows
        
        # Disputed escrows
        disputed_escrows = EscrowTransaction.objects.filter(
            order__seller=user,
            status=EscrowTransaction.Status.DISPUTED
        ).select_related('order', 'buyer').order_by('-dispute_opened_at')
        ctx['disputed_escrows'] = disputed_escrows
        
        # Calculate awaiting payment (orders that have shipped but funds not yet released)
        awaiting_payment_total = pending_escrows.aggregate(total=Sum('amount'))['total'] or 0
        ctx['awaiting_payment'] = awaiting_payment_total
        
        return ctx

