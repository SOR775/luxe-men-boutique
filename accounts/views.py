"""
accounts/views.py — Authentication & Profile Views
"""
import secrets
import logging
import threading
from datetime import timedelta

from django.contrib import messages, auth
from django.contrib.auth import get_user_model, login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import HttpResponse
import csv
import io
import json
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, F
from django.utils import timezone

from support.models import SupportTicket

from orders.models import Order, OrderItem, Coupon
from inventory.models import Stock
from products.models import Product
from payments.models import Payment
from escrow.models import EscrowTransaction

from .forms import (
    RegistrationForm, LoginForm, ProfileUpdateForm, AddressForm,
    PasswordChangeForm, ForgotPasswordForm, ResetPasswordForm,
    AdminUserForm, StaffRoleAssignmentForm,
)
from .models import (
    EmailVerificationToken, PasswordResetToken, EmailLoginCode,
    UserAddress, LoginHistory, ActivityLog,
    Administrator, AuditLog,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def build_public_url(request, path):
    """Build an absolute URL for emails using the public request host when available."""
    if not path.startswith('/'):
        path = f'/{path}'

    forwarded_host = request.META.get('HTTP_X_FORWARDED_HOST') or request.META.get('HTTP_HOST')
    forwarded_proto = (
        request.META.get('HTTP_X_FORWARDED_PROTO')
        or request.META.get('HTTP_X_FORWARDED_SCHEME')
        or request.scheme
    )

    if forwarded_host:
        host = forwarded_host.split(',')[0].strip()
        host_name = host.split(':')[0]
        if host_name not in {'localhost', '127.0.0.1', '0.0.0.0'}:
            return f"{forwarded_proto}://{host}{path}"

    site_url = getattr(settings, 'SITE_URL', '').strip()
    if site_url:
        return f"{site_url.rstrip('/')}{path}"

    return request.build_absolute_uri(path)


def get_client_ip(request):
    """Extract the real client IP from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_login_event(user, request, status, email_attempted=''):
    """Record a login event to the audit trail."""
    LoginHistory.objects.create(
        user=user,
        email_attempted=email_attempted or (user.email if user else ''),
        status=status,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )


# ─── Registration ──────────────────────────────────────────────────────────────

class RegisterView(View):
    """Customer registration with email verification."""
    template_name = 'accounts/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = RegistrationForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            self._send_verification_email(user, request)
            messages.success(
                request,
                f'Welcome! A verification email has been sent to {user.email}. '
                f'Please verify your account before logging in.'
            )
            return redirect('accounts:login')

        return render(request, self.template_name, {'form': form})

    def _send_verification_email(self, user, request):
        """Generate token and send verification email."""
        token_str = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(hours=24)

        EmailVerificationToken.objects.update_or_create(
            user=user,
            defaults={
                'token': token_str,
                'expires_at': expires_at,
                'is_used': False,
            }
        )

        verify_url = build_public_url(request, f"/accounts/verify-email/{token_str}/")
        subject = f'Verify your {settings.SITE_NAME} account'
        html_message = render_to_string('accounts/emails/verify_email.html', {
            'user': user,
            'verify_url': verify_url,
            'site_name': settings.SITE_NAME,
        })

        def _send():
            try:
                send_mail(
                    subject=subject,
                    message=f'Click here to verify your email: {verify_url}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f'Failed to send verification email to {user.email}: {e}')
        threading.Thread(target=_send, daemon=True).start()


# ─── Email Verification ────────────────────────────────────────────────────────

class VerifyEmailView(View):
    """Process email verification token."""

    def get(self, request, token):
        try:
            vt = EmailVerificationToken.objects.select_related('user').get(token=token)
        except EmailVerificationToken.DoesNotExist:
            messages.error(request, 'Invalid verification link.')
            return redirect('accounts:login')

        if not vt.is_valid():
            messages.error(request, 'This verification link has expired. Please request a new one.')
            return redirect('accounts:resend_verification')

        vt.user.is_email_verified = True
        vt.user.save(update_fields=['is_email_verified'])
        vt.is_used = True
        vt.save(update_fields=['is_used'])

        messages.success(request, 'Your email has been verified! You can now log in.')
        return redirect('accounts:login')


class ResendVerificationView(View):
    """Resend verification email."""
    template_name = 'accounts/resend_verification.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        try:
            user = User.objects.get(email=email, is_email_verified=False)
            RegisterView()._send_verification_email(user, request)
            messages.success(request, f'Verification email resent to {email}.')
        except User.DoesNotExist:
            messages.info(request, 'If that email is registered and unverified, we sent a link.')
        return redirect('accounts:login')


# ─── Login ────────────────────────────────────────────────────────────────────

class LoginView(View):
    """Login with account lockout protection."""
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = LoginForm(request)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = LoginForm(request, data=request.POST)
        email_attempted = request.POST.get('username', '')

        # Find user to check lockout
        try:
            if '@' in email_attempted:
                user_check = User.objects.get(email=email_attempted.lower())
            else:
                user_check = User.objects.get(username=email_attempted)

            if user_check.is_locked:
                remaining = (user_check.locked_until - timezone.now()).seconds // 60
                messages.error(
                    request,
                    f'Account is locked due to too many failed attempts. '
                    f'Try again in {remaining} minutes.'
                )
                log_login_event(None, request, LoginHistory.LoginStatus.LOCKED, email_attempted)
                return render(request, self.template_name, {'form': form})
        except User.DoesNotExist:
            pass

        if form.is_valid():
            user = form.get_user()

            if not user.is_email_verified:
                messages.warning(
                    request,
                    'Please verify your email address before logging in. '
                    '<a href="/accounts/resend-verification/">Resend verification email</a>.'
                )
                return render(request, self.template_name, {'form': form})

            # Reset failed attempts on successful login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_ip = get_client_ip(request)
            user.save(update_fields=['failed_login_attempts', 'locked_until', 'last_login_ip'])

            # Staff accounts require a second factor before the session is established.
            if user.is_staff:
                code = ''.join(secrets.choice('0123456789') for _ in range(6))
                expires_at = timezone.now() + timedelta(minutes=settings.EMAIL_LOGIN_CODE_EXPIRY_MINUTES)
                EmailLoginCode.objects.create(
                    user=user, email=user.email, code=code, expires_at=expires_at,
                )
                self._send_2fa_email(user, code)

                request.session['pending_2fa_user_id'] = str(user.pk)
                request.session['pending_2fa_remember_me'] = bool(form.cleaned_data.get('remember_me'))
                request.session['pending_2fa_next'] = request.GET.get('next', '')
                return redirect('accounts:staff_2fa_verify')

            # Handle remember-me
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)  # Session expires on browser close
            else:
                request.session.set_expiry(settings.SESSION_COOKIE_AGE)

            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            log_login_event(user, request, LoginHistory.LoginStatus.SUCCESS)

            next_url = request.GET.get('next', 'core:home')
            messages.success(request, f'Welcome back, {user.get_short_name()}!')
            return redirect(next_url)

        else:
            # Increment failed attempts
            try:
                if '@' in email_attempted:
                    failed_user = User.objects.get(email=email_attempted.lower())
                else:
                    failed_user = User.objects.get(username=email_attempted)

                failed_user.failed_login_attempts += 1
                max_attempts = getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5)

                if failed_user.failed_login_attempts >= max_attempts:
                    lockout_minutes = getattr(settings, 'LOCKOUT_DURATION_MINUTES', 30)
                    failed_user.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
                    messages.error(
                        request,
                        f'Too many failed attempts. Account locked for {lockout_minutes} minutes.'
                    )

                failed_user.save(update_fields=['failed_login_attempts', 'locked_until'])
                log_login_event(failed_user, request, LoginHistory.LoginStatus.FAILED)
            except User.DoesNotExist:
                log_login_event(None, request, LoginHistory.LoginStatus.FAILED, email_attempted)

        return render(request, self.template_name, {'form': form})

    @staticmethod
    def _send_2fa_email(user, code):
        subject = f'Your {settings.SITE_NAME} staff sign-in code'
        html_message = render_to_string('accounts/emails/login_code.html', {
            'user': user,
            'code': code,
            'expiry_minutes': settings.EMAIL_LOGIN_CODE_EXPIRY_MINUTES,
            'site_name': settings.SITE_NAME,
        })
        send_mail(
            subject=subject,
            message=f'Your staff sign-in code is: {code}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )


class StaffTwoFactorVerifyView(View):
    """
    Second step of staff login: the account/password has already been
    confirmed in LoginView, and a one-time code was emailed. The Django
    session is only established once this code is verified, so a stolen
    password alone is never enough to reach the admin dashboard.
    """
    template_name = 'accounts/login_2fa_verify.html'

    def _pending_user(self, request):
        user_id = request.session.get('pending_2fa_user_id')
        if not user_id:
            return None
        try:
            return User.objects.get(pk=user_id, is_staff=True, is_active=True)
        except (User.DoesNotExist, ValueError):
            return None

    def get(self, request):
        if not self._pending_user(request):
            return redirect('accounts:login')
        return render(request, self.template_name, {})

    def post(self, request):
        user = self._pending_user(request)
        if not user:
            messages.error(request, 'Your sign-in attempt expired. Please log in again.')
            return redirect('accounts:login')

        code = request.POST.get('code', '').strip()
        try:
            login_code = EmailLoginCode.objects.get(user=user, code=code, is_used=False)
        except EmailLoginCode.DoesNotExist:
            messages.error(request, 'Invalid code. Please try again.')
            return render(request, self.template_name, {})

        if not login_code.is_valid():
            messages.error(request, 'This code has expired. Please log in again to request a new one.')
            return redirect('accounts:login')

        login_code.mark_used()

        remember_me = request.session.pop('pending_2fa_remember_me', False)
        next_url = request.session.pop('pending_2fa_next', '') or 'core:home'
        request.session.pop('pending_2fa_user_id', None)

        if not remember_me:
            request.session.set_expiry(0)
        else:
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)

        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        log_login_event(user, request, LoginHistory.LoginStatus.SUCCESS)
        messages.success(request, f'Welcome back, {user.get_short_name()}!')
        return redirect(next_url)


class EmailLoginCodeRequestView(View):
    """Send a one-time email login code to verified users."""
    template_name = 'accounts/login_code_request.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        from .forms import EmailLoginRequestForm
        return render(request, self.template_name, {'form': EmailLoginRequestForm()})

    def post(self, request):
        from .forms import EmailLoginRequestForm
        form = EmailLoginRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email, is_active=True)
                if user.is_email_verified:
                    code = ''.join(secrets.choice('0123456789') for _ in range(6))
                    expires_at = timezone.now() + timedelta(minutes=settings.EMAIL_LOGIN_CODE_EXPIRY_MINUTES)
                    EmailLoginCode.objects.create(
                        user=user,
                        email=user.email,
                        code=code,
                        expires_at=expires_at,
                    )
                    self._send_login_code_email(user, code)
            except User.DoesNotExist:
                pass

            messages.success(
                request,
                'If that email is registered and verified, a one-time login code has been sent.'
            )
            return redirect('accounts:login_code_verify')

        return render(request, self.template_name, {'form': form})

    def _send_login_code_email(self, user, code):
        subject = f'Your {settings.SITE_NAME} login code'
        html_message = render_to_string('accounts/emails/login_code.html', {
            'user': user,
            'code': code,
            'expiry_minutes': settings.EMAIL_LOGIN_CODE_EXPIRY_MINUTES,
            'site_name': settings.SITE_NAME,
        })
        send_mail(
            subject=subject,
            message=f'Use this code to sign in: {code}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )


class EmailLoginCodeVerifyView(View):
    """Verify the one-time email login code."""
    template_name = 'accounts/login_code_verify.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        from .forms import EmailLoginCodeForm
        return render(request, self.template_name, {'form': EmailLoginCodeForm()})

    def post(self, request):
        from .forms import EmailLoginCodeForm
        form = EmailLoginCodeForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            code = form.cleaned_data['code']
            try:
                login_code = EmailLoginCode.objects.select_related('user').get(
                    email=email,
                    code=code,
                    is_used=False,
                )
            except EmailLoginCode.DoesNotExist:
                messages.error(request, 'Invalid login code.')
                return render(request, self.template_name, {'form': form})

            if not login_code.is_valid():
                messages.error(request, 'This login code has expired or already been used.')
                return render(request, self.template_name, {'form': form})

            user = login_code.user
            if not user.is_active or not user.is_email_verified:
                messages.error(request, 'Unable to sign in with this account. Please contact support.')
                return redirect('accounts:login')

            login_code.mark_used()
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            log_login_event(user, request, LoginHistory.LoginStatus.SUCCESS)
            messages.success(request, 'Signed in successfully.')
            return redirect('core:home')

        return render(request, self.template_name, {'form': form})


# ─── Logout ───────────────────────────────────────────────────────────────────

class LogoutView(View):
    def post(self, request):
        if request.user.is_authenticated:
            log_login_event(request.user, request, LoginHistory.LoginStatus.LOGOUT)
        logout(request)
        messages.success(request, 'You have been logged out. See you soon!')
        return redirect('core:home')


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    """Staff-only admin dashboard with key metrics and placeholders for charts."""
    template_name = 'accounts/admin_dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if request.user.is_staff or request.user.has_admin_permission('access_admin_dashboard'):
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # High-level metrics
        ctx['orders_count'] = Order.objects.count()
        ctx['total_revenue'] = Order.objects.aggregate(total=Sum('total'))['total'] or 0
        ctx['customers_count'] = User.objects.count()
        ctx['products_count'] = Product.objects.filter(visibility=Product.Visibility.PUBLISHED).count()
        ctx['coupons_count'] = Coupon.objects.count()

        ctx['orders_by_status'] = dict(
            Order.objects.values('status').annotate(count=Count('id')).values_list('status', 'count')
        )
        attention_filter = self.request.GET.get('alert_type', '').strip().lower()
        attention_state = self.request.GET.get('alert_state', 'open').strip().lower()
        if attention_state not in {'open', 'resolved'}:
            attention_state = 'open'

        session = getattr(self.request, 'session', None)
        reviewed_alerts = []
        if session is not None:
            reviewed_alerts = session.get('reviewed_dashboard_alerts', []) or []
        if not isinstance(reviewed_alerts, list):
            reviewed_alerts = list(reviewed_alerts)

        reviewed_key = self.request.GET.get('reviewed', '').strip()
        if reviewed_key and session is not None:
            if reviewed_key not in reviewed_alerts:
                reviewed_alerts.append(reviewed_key)
                session['reviewed_dashboard_alerts'] = reviewed_alerts
                session.modified = True

        ctx['attention_filter'] = attention_filter
        ctx['attention_state'] = attention_state
        ctx['reviewed_alert_count'] = len(reviewed_alerts)

        open_payment_statuses = [
            Payment.Status.FAILED,
            Payment.Status.PENDING,
            Payment.Status.PROCESSING,
        ]
        resolved_payment_statuses = [
            Payment.Status.COMPLETED,
            Payment.Status.REFUNDED,
            Payment.Status.CANCELLED,
        ]

        if attention_state == 'resolved':
            payment_alert_qs = Payment.objects.filter(
                status__in=resolved_payment_statuses
            ).select_related('order').order_by('-updated_at')
        else:
            payment_alert_qs = Payment.objects.filter(
                status__in=open_payment_statuses
            ).select_related('order').order_by('-created_at')

        payment_alerts = list(payment_alert_qs[:8])
        ctx['payment_alert_count'] = payment_alert_qs.count()
        ctx['payment_alerts'] = payment_alerts

        if attention_state == 'resolved':
            escrow_alert_qs = EscrowTransaction.objects.filter(
                status__in=[
                    EscrowTransaction.Status.RELEASED,
                    EscrowTransaction.Status.REFUNDED,
                    EscrowTransaction.Status.CANCELLED,
                ]
            ).select_related('order', 'payment').order_by('-updated_at')
        else:
            escrow_alert_qs = EscrowTransaction.objects.exclude(
                status__in=[
                    EscrowTransaction.Status.RELEASED,
                    EscrowTransaction.Status.REFUNDED,
                    EscrowTransaction.Status.CANCELLED,
                ]
            ).select_related('order', 'payment').order_by('-created_at')

        escrow_alerts = list(escrow_alert_qs[:8])
        ctx['escrow_alert_count'] = escrow_alert_qs.count()
        ctx['escrow_alerts'] = escrow_alerts

        attention_queue = []
        for payment in payment_alerts:
            payment_age = timezone.now() - payment.created_at
            age_display = 'just now'
            if payment_age.days:
                age_display = f"{payment_age.days}d ago"
            elif payment_age.seconds >= 3600:
                age_display = f"{payment_age.seconds // 3600}h ago"
            elif payment_age.seconds >= 60:
                age_display = f"{payment_age.seconds // 60}m ago"

            attention_queue.append({
                'kind': 'payment',
                'payment_id': str(payment.id),
                'title': f"Order {payment.order.order_number}",
                'detail': f"{payment.get_status_display()} — {payment.method.upper()} payment",
                'priority': 'high' if payment.status == Payment.Status.FAILED else 'medium',
                'action_url': reverse('orders:order_detail', kwargs={'order_number': payment.order.order_number}),
                'action_label': 'Open Order',
                'review_url': f"{reverse('accounts:admin_dashboard')}?alert_state={attention_state}&reviewed=payment:{payment.id}",
                'age_display': age_display,
                'state': 'resolved' if payment.status in resolved_payment_statuses else 'open',
            })

        for escrow in escrow_alerts:
            escrow_age = timezone.now() - escrow.created_at
            age_display = 'just now'
            if escrow_age.days:
                age_display = f"{escrow_age.days}d ago"
            elif escrow_age.seconds >= 3600:
                age_display = f"{escrow_age.seconds // 3600}h ago"
            elif escrow_age.seconds >= 60:
                age_display = f"{escrow_age.seconds // 60}m ago"

            attention_queue.append({
                'kind': 'escrow',
                'escrow_id': str(escrow.id),
                'title': f"Order {escrow.order.order_number}",
                'detail': f"Escrow {escrow.get_status_display()}",
                'priority': 'high' if escrow.status in {EscrowTransaction.Status.DISPUTED, EscrowTransaction.Status.SHIPPED} else 'medium',
                'action_url': reverse('escrow:status', kwargs={'escrow_id': escrow.id}),
                'action_label': 'Review Escrow',
                'release_url': reverse('escrow:release', kwargs={'escrow_id': escrow.id}),
                'review_url': f"{reverse('accounts:admin_dashboard')}?alert_state={attention_state}&reviewed=escrow:{escrow.id}",
                'age_display': age_display,
                'state': 'resolved' if escrow.status in {EscrowTransaction.Status.RELEASED, EscrowTransaction.Status.REFUNDED, EscrowTransaction.Status.CANCELLED} else 'open',
            })

        if attention_filter in {'payment', 'escrow'}:
            attention_queue = [item for item in attention_queue if item['kind'] == attention_filter]

        reviewed_queue = []
        for item in attention_queue:
            key = f"{item['kind']}:{item.get('payment_id') or item.get('escrow_id')}"
            if key in reviewed_alerts:
                continue

            if attention_state == 'resolved':
                if item['state'] == 'resolved':
                    reviewed_queue.append(item)
            else:
                if item['state'] == 'open':
                    reviewed_queue.append(item)

        attention_queue = reviewed_queue
        attention_queue.sort(key=lambda item: (0 if item['priority'] == 'high' else 1, item['title']))
        ctx['attention_queue'] = attention_queue

        # Low stock count
        ctx['low_stock_count'] = Stock.objects.filter(quantity__lte=F('low_stock_threshold')).count()

        # Recent orders (latest 10)
        ctx['recent_orders'] = Order.objects.select_related('user').order_by('-created_at')[:10]

        # Top selling products (by quantity) - aggregated from OrderItem
        top = (
            OrderItem.objects.values('product_name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')[:6]
        )
        ctx['top_selling'] = list(top)

        # Revenue last 7 days (simple aggregation)
        from datetime import timedelta
        from support.models import SupportMessage, SupportTicket

        today = timezone.now().date()
        last7 = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            start = timezone.datetime.combine(day, timezone.datetime.min.time()).replace(tzinfo=timezone.get_current_timezone())
            end = timezone.datetime.combine(day, timezone.datetime.max.time()).replace(tzinfo=timezone.get_current_timezone())
            total = Order.objects.filter(created_at__range=(start, end)).aggregate(total=Sum('total'))['total'] or 0
            last7.append({'date': day.isoformat(), 'total': float(total)})

        ctx['revenue_last_7'] = last7
        try:
            ctx['revenue_last_7_json'] = json.dumps(last7)
        except Exception:
            ctx['revenue_last_7_json'] = '[]'

        try:
            ctx['top_selling_json'] = json.dumps(ctx.get('top_selling', []))
        except Exception:
            ctx['top_selling_json'] = '[]'

        open_tickets = (
            SupportTicket.objects.select_related('user')
            .prefetch_related('messages')
            .filter(status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.PENDING])
            .order_by('-updated_at')[:8]
        )
        ctx['support_tickets'] = list(open_tickets)
        ctx['support_ticket_messages'] = {
            ticket.pk: list(ticket.messages.order_by('-created_at')[:2])
            for ticket in open_tickets
        }
        return ctx


# ─── Password Reset ───────────────────────────────────────────────────────────

class ForgotPasswordView(View):
    template_name = 'accounts/forgot_password.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ForgotPasswordForm()})

    def post(self, request):
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].lower()
            try:
                user = User.objects.get(email=email)
                self._send_reset_email(user, request)
            except User.DoesNotExist:
                pass  # Don't reveal if email exists

            messages.success(
                request,
                'If that email is registered, you will receive a reset link shortly.'
            )
            return redirect('accounts:login')

        return render(request, self.template_name, {'form': form})

    def _send_reset_email(self, user, request):
        token_str = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(hours=2)

        PasswordResetToken.objects.create(
            user=user,
            token=token_str,
            expires_at=expires_at,
        )

        reset_url = build_public_url(request, f"/accounts/reset-password/{token_str}/")
        send_mail(
            subject=f'Reset your {settings.SITE_NAME} password',
            message=f'Reset your password here: {reset_url}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=render_to_string('accounts/emails/reset_password.html', {
                'user': user,
                'reset_url': reset_url,
                'site_name': settings.SITE_NAME,
            }),
            fail_silently=False,
        )


class ResetPasswordView(View):
    template_name = 'accounts/reset_password.html'

    def get(self, request, token):
        try:
            rt = PasswordResetToken.objects.select_related('user').get(token=token)
            if not rt.is_valid():
                messages.error(request, 'This link has expired.')
                return redirect('accounts:forgot_password')
        except PasswordResetToken.DoesNotExist:
            messages.error(request, 'Invalid reset link.')
            return redirect('accounts:forgot_password')

        return render(request, self.template_name, {
            'form': ResetPasswordForm(),
            'token': token,
        })

    def post(self, request, token):
        try:
            rt = PasswordResetToken.objects.select_related('user').get(token=token)
            if not rt.is_valid():
                messages.error(request, 'This link has expired.')
                return redirect('accounts:forgot_password')
        except PasswordResetToken.DoesNotExist:
            messages.error(request, 'Invalid reset link.')
            return redirect('accounts:forgot_password')

        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user = rt.user
            user.set_password(form.cleaned_data['password'])
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save()
            rt.is_used = True
            rt.save()
            messages.success(request, 'Password reset successfully. Please log in.')
            return redirect('accounts:login')

        return render(request, self.template_name, {'form': form, 'token': token})


# ─── Profile ──────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class ProfileView(View):
    template_name = 'accounts/profile.html'

    def get(self, request):
        form = ProfileUpdateForm(instance=request.user)
        addresses = UserAddress.objects.filter(user=request.user)
        return render(request, self.template_name, {
            'form': form,
            'addresses': addresses,
        })

    def post(self, request):
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')

        addresses = UserAddress.objects.filter(user=request.user)
        return render(request, self.template_name, {
            'form': form,
            'addresses': addresses,
        })


@method_decorator(login_required, name='dispatch')
class SupportHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/support_history.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tickets'] = (
            SupportTicket.objects.filter(user=self.request.user)
            .prefetch_related('messages')
            .order_by('-updated_at')
        )
        return ctx


class SupportHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/support_history.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tickets'] = (
            SupportTicket.objects.filter(user=self.request.user)
            .prefetch_related('messages')
            .order_by('-updated_at')
        )
        return ctx


class DashboardView(TemplateView):
    template_name = 'accounts/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        try:
            from orders.models import Order
            context['recent_orders'] = Order.objects.filter(
                user=user
            ).order_by('-created_at')[:5]
            context['total_orders'] = Order.objects.filter(user=user).count()
        except Exception:
            context['recent_orders'] = []
            context['total_orders'] = 0

        try:
            from products.models import WishlistItem
            context['wishlist_count'] = WishlistItem.objects.filter(user=user).count()
        except Exception:
            context['wishlist_count'] = 0

        try:
            from accounts.models import UserAddress
            addresses = UserAddress.objects.filter(user=user)
            context['address_count'] = addresses.count()
            context['default_address'] = addresses.filter(is_default=True).first()
        except Exception:
            context['address_count'] = 0
            context['default_address'] = None

        try:
            from orders.models import ReturnRequest
            context['return_count'] = ReturnRequest.objects.filter(order__user=user).count()
        except Exception:
            context['return_count'] = 0

        try:
            from wallets.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=user)
            context['wallet_balance'] = wallet.balance
            context['wallet_currency'] = wallet.currency
            context['wallet_transactions_count'] = wallet.transactions.count()
        except Exception:
            context['wallet_balance'] = 0
            context['wallet_currency'] = 'KES'
            context['wallet_transactions_count'] = 0

        context['loyalty_points'] = user.loyalty_points
        context['referral_code'] = getattr(user, 'referral_code', '')
        return context


# ─── Address Book ─────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class AddressListView(View):
    template_name = 'accounts/addresses.html'

    def get(self, request):
        addresses = UserAddress.objects.filter(user=request.user)
        return render(request, self.template_name, {
            'addresses': addresses,
            'form': AddressForm(),
        })


@method_decorator(login_required, name='dispatch')
class AddressCreateView(View):
    def post(self, request):
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, 'Address added successfully.')
        return redirect('accounts:addresses')


@method_decorator(login_required, name='dispatch')
class AddressDeleteView(View):
    def post(self, request, pk):
        address = get_object_or_404(UserAddress, pk=pk, user=request.user)
        address.delete()
        messages.success(request, 'Address removed.')
        return redirect('accounts:addresses')


# ─── Change Password ──────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class ChangePasswordView(View):
    template_name = 'accounts/change_password.html'

    def get(self, request):
        return render(request, self.template_name, {'form': PasswordChangeForm()})

    def post(self, request):
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            user = request.user
            if not user.check_password(form.cleaned_data['current_password']):
                form.add_error('current_password', 'Incorrect current password.')
                return render(request, self.template_name, {'form': form})

            user.set_password(form.cleaned_data['new_password'])
            user.save()
            # Keep user logged in after password change
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully.')
            return redirect('accounts:profile')

        return render(request, self.template_name, {'form': form})


# ─── Login History ─────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class LoginHistoryView(TemplateView):
    template_name = 'accounts/login_history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import LoginHistory
        context['history'] = LoginHistory.objects.filter(
            user=self.request.user
        ).order_by('-created_at')[:50]
        return context


@method_decorator(login_required, name='dispatch')
class ReturnRequestsView(TemplateView):
    template_name = 'accounts/returns.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from orders.models import ReturnRequest
        context['returns'] = ReturnRequest.objects.filter(order__user=self.request.user).select_related('order').order_by('-created_at')
        return context


# ─── Admin: User Management ──────────────────────────────────────────────────


class AdminUserListView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/admin/users_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_user_management'):
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = User.objects.all().order_by('-created_at')
        page = self.request.GET.get('page', 1)
        paginator = Paginator(qs, 25)
        try:
            users_page = paginator.page(page)
        except PageNotAnInteger:
            users_page = paginator.page(1)
        except EmptyPage:
            users_page = paginator.page(paginator.num_pages)

        context['users'] = users_page.object_list
        context['paginator'] = paginator
        context['page_obj'] = users_page
        return context


class AdminUserEditView(LoginRequiredMixin, View):
    template_name = 'accounts/admin/user_edit.html'

    def dispatch(self, request, pk, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_user_management'):
            return redirect('accounts:dashboard')
        self.target = get_object_or_404(User, pk=pk)
        return super().dispatch(request, pk, *args, **kwargs)

    def get(self, request, pk):
        form = AdminUserForm(instance=self.target)
        admin_profile, _ = Administrator.objects.get_or_create(user=self.target)
        role_form = StaffRoleAssignmentForm(instance=admin_profile)
        return render(request, self.template_name, {
            'form': form,
            'target': self.target,
            'role_form': role_form,
            'can_manage_roles': request.user.is_super_admin or request.user.has_admin_permission('manage_staff_roles'),
        })

    def post(self, request, pk):
        form = AdminUserForm(request.POST, instance=self.target)
        admin_profile, _ = Administrator.objects.get_or_create(user=self.target)
        role_form = StaffRoleAssignmentForm(request.POST, instance=admin_profile)
        if form.is_valid() and role_form.is_valid():
            form.save()
            if request.user.is_super_admin or request.user.has_admin_permission('manage_staff_roles'):
                role_form.save()
                try:
                    old_role_names = list(admin_profile.roles.values_list('name', flat=True))
                    new_role_names = list(role_form.cleaned_data.get('roles', []).values_list('name', flat=True))
                    AuditLog.objects.create(
                        actor=request.user,
                        target_user=self.target,
                        action='role_change',
                        message=f'Admin updated role membership for {self.target.email}',
                        metadata={'old_roles': list(old_role_names), 'new_roles': list(new_role_names)},
                        ip_address=get_client_ip(request),
                    )
                except Exception:
                    logger.exception('Failed to write role audit log')
            try:
                AuditLog.objects.create(
                    actor=request.user,
                    target_user=self.target,
                    action='user_update',
                    message=f'Admin updated user {self.target.email}',
                    metadata={'fields': list(form.cleaned_data.keys())},
                    ip_address=get_client_ip(request),
                )
            except Exception:
                logger.exception('Failed to write audit log')

            messages.success(request, 'User updated successfully.')
            return redirect('accounts:admin_users')
        return render(request, self.template_name, {
            'form': form,
            'target': self.target,
            'role_form': role_form,
            'can_manage_roles': request.user.is_super_admin or request.user.has_admin_permission('manage_staff_roles'),
        })


class AdminUserPasswordResetView(LoginRequiredMixin, View):
    """Allow staff to trigger a password-reset email to a user on request."""

    def dispatch(self, request, pk, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_user_management'):
            return JsonResponse({'success': False, 'error': 'forbidden'}, status=403)
        self.target = get_object_or_404(User, pk=pk)
        return super().dispatch(request, pk, *args, **kwargs)

    def post(self, request, pk):
        # Use existing ForgotPassword logic: create a PasswordResetToken and email
        try:
            token_str = secrets.token_urlsafe(48)
            expires_at = timezone.now() + timedelta(hours=2)
            from .models import PasswordResetToken
            PasswordResetToken.objects.create(user=self.target, token=token_str, expires_at=expires_at)
            reset_url = build_public_url(request, f"/accounts/reset-password/{token_str}/")
            send_mail(
                subject=f'Reset your {settings.SITE_NAME} password',
                message=f'Reset your password here: {reset_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.target.email],
                html_message=render_to_string('accounts/emails/reset_password.html', {
                    'user': self.target,
                    'reset_url': reset_url,
                    'site_name': settings.SITE_NAME,
                }),
                fail_silently=False,
            )
            # audit the reset
            try:
                from .models import AuditLog
                AuditLog.objects.create(
                    actor=request.user,
                    target_user=self.target,
                    action='password_reset',
                    message=f'Admin triggered password reset for {self.target.email}',
                    metadata={'initiated_by_admin': True},
                    ip_address=get_client_ip(request),
                )
            except Exception:
                logger.exception('Failed to write audit log')

            return JsonResponse({'success': True})
        except Exception:
            logger.exception('Failed to trigger password reset')
            return JsonResponse({'success': False, 'error': 'failed'}, status=500)


class AdminAuditLogListView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/admin/audit_log.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_audit_log'):
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = AuditLog.objects.select_related('actor', 'target_user').all()

        # simple filters: ?q=search, ?action=action, ?user=uuid
        q = self.request.GET.get('q')
        action = self.request.GET.get('action')
        user = self.request.GET.get('user')
        if q:
            qs = qs.filter(Q(message__icontains=q) | Q(actor__email__icontains=q) | Q(target_user__email__icontains=q))
        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(Q(target_user__id=user) | Q(actor__id=user))

        page = self.request.GET.get('page', 1)
        paginator = Paginator(qs.order_by('-created_at'), 50)
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        context['logs'] = page_obj.object_list
        context['paginator'] = paginator
        context['page_obj'] = page_obj
        context['actions'] = dict(AuditLog.ACTION_CHOICES)
        return context


class AdminAuditLogDetailView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/admin/audit_detail.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_audit_log'):
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get('pk')
        log = get_object_or_404(AuditLog, pk=pk)
        context['log'] = log
        try:
            context['metadata_pretty'] = json.dumps(log.metadata or {}, indent=2)
        except Exception:
            context['metadata_pretty'] = '{}'
        return context


class AdminAuditLogExportCSVView(LoginRequiredMixin, View):
    """Export audit log entries as CSV. Honors same filters as list view via query params."""

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return redirect('accounts:login')
        if not request.user.has_admin_permission('access_audit_log'):
            return JsonResponse({'success': False, 'error': 'forbidden'}, status=403)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        qs = AuditLog.objects.select_related('actor', 'target_user').all()
        q = request.GET.get('q')
        action = request.GET.get('action')
        user = request.GET.get('user')
        if q:
            qs = qs.filter(Q(message__icontains=q) | Q(actor__email__icontains=q) | Q(target_user__email__icontains=q))
        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(Q(target_user__id=user) | Q(actor__id=user))

        # prepare CSV
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['created_at', 'action', 'actor_email', 'target_email', 'message', 'metadata', 'ip_address'])
        for log in qs.order_by('-created_at'):
            writer.writerow([
                log.created_at.isoformat(),
                log.action,
                log.actor.email if log.actor else '',
                log.target_user.email if log.target_user else '',
                (log.message or '').replace('\n', ' '),
                json.dumps(log.metadata or {}),
                log.ip_address or '',
            ])

        resp = HttpResponse(buffer.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="audit_log_export.csv"'
        return resp
        


@method_decorator(login_required, name='dispatch')
class WishlistView(TemplateView):
    """View to list the user's wishlist."""
    template_name = 'accounts/wishlist.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from products.models import WishlistItem, ProductImage
        from django.db.models import Prefetch
        context['wishlist_items'] = WishlistItem.objects.filter(
            user=self.request.user
        ).select_related('product').prefetch_related(
            Prefetch('product__images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
        )
        return context
