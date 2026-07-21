"""
core/admin_views.py — Admin Dashboard Views for System Management
"""
import os
try:
    import psutil
except Exception:
    psutil = None
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from django.db import transaction
from django.core.exceptions import PermissionDenied

from accounts.models import User
from core.admin_models import SystemSettings, ContentModerationQueue, UserSuspension
from escrow.models import EscrowTransaction

from accounts.models import User, AuditLog
from accounts.views import get_client_ip
from core.admin_models import SystemSettings, ContentModerationQueue, UserSuspension


def staff_required(user):
    """Check if user is staff with a valid admin role profile."""
    return user.is_staff and user.has_admin_permission('access_admin_dashboard')


def requires_permission(codename):
    """Role-aware permission guard for admin class-based views."""
    def _check(user):
        return user.is_staff and user.has_admin_permission(codename)
    return _check


class AdminSystemHealthView(LoginRequiredMixin, TemplateView):
    """Display system health monitoring dashboard."""
    template_name = 'admin/system_health.html'
    
    @method_decorator(user_passes_test(requires_permission('access_system_health')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Database size
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT sum(page_count * page_size) as size 
                    FROM pragma_page_count(), pragma_page_size()
                """)
                db_size = cursor.fetchone()[0] or 0
                # Convert to MB
                db_size_mb = round(db_size / (1024 * 1024), 2)
        except:
            db_size_mb = 'N/A'
        
        # System stats
        try:
            if psutil:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
            else:
                cpu_percent = memory = disk = None
        except Exception:
            cpu_percent = memory = disk = None
        
        context['database_size_mb'] = db_size_mb
        context['cpu_percent'] = cpu_percent
        context['memory'] = memory
        context['disk'] = disk
        
        # User statistics
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['sellers'] = User.objects.filter(sales__isnull=False).distinct().count()
        context['suspended_users'] = UserSuspension.objects.filter(is_active=True).count()
        
        # Recent activity
        context['new_users_today'] = User.objects.filter(
            created_at__date=timezone.now().date()
        ).count()
        
        # Order statistics
        from orders.models import Order
        context['orders_today'] = Order.objects.filter(
            created_at__date=timezone.now().date()
        ).count()
        
        return context


class AdminUserManagementView(LoginRequiredMixin, TemplateView):
    """Manage users: view, suspend, ban."""
    template_name = 'admin/user_management.html'
    
    @method_decorator(user_passes_test(requires_permission('access_user_management')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters
        search_query = self.request.GET.get('search', '')
        user_type = self.request.GET.get('type', '')
        status_filter = self.request.GET.get('status', '')
        
        # Base queryset
        users = User.objects.select_related('suspension').prefetch_related('sales')
        
        # Search
        if search_query:
            users = users.filter(
                Q(email__icontains=search_query) |
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )
        
        # Type filter
        if user_type == 'sellers':
            users = users.filter(sales__isnull=False).distinct()
        elif user_type == 'customers':
            users = users.filter(sales__isnull=True)
        elif user_type == 'admin':
            users = users.filter(is_staff=True)
        
        # Status filter
        if status_filter == 'active':
            users = users.filter(is_active=True)
        elif status_filter == 'suspended':
            users = users.filter(suspension__is_active=True).distinct()
        elif status_filter == 'inactive':
            users = users.filter(is_active=False)
        
        context['users'] = users.order_by('-created_at')[:100]
        context['total_users'] = User.objects.count()
        context['search_query'] = search_query
        context['user_type'] = user_type
        context['status_filter'] = status_filter
        
        return context


class AdminSuspendUserView(LoginRequiredMixin, View):
    """Suspend or ban a user."""
    
    @method_decorator(user_passes_test(requires_permission('access_user_management')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        # A staff member can never suspend someone with equal or higher
        # privilege than themselves — otherwise a single compromised or
        # rogue staff account with only 'access_user_management' could
        # lock out super-admins or peer staff.
        if user.is_staff and not request.user.is_super_admin:
            raise PermissionDenied("You don't have permission to suspend a staff account.")
        if user.pk == request.user.pk:
            raise PermissionDenied("You can't suspend your own account.")

        suspension_type = request.POST.get('suspension_type', 'suspended')
        reason = request.POST.get('reason', '')
        days = request.POST.get('days')
        
        # Set suspension end date
        suspended_until = None
        if days and suspension_type == 'suspended':
            try:
                suspended_until = timezone.now() + timedelta(days=int(days))
            except (ValueError, TypeError):
                pass
        
        # Create or update suspension
        suspension, created = UserSuspension.objects.get_or_create(user=user)
        suspension.suspension_type = suspension_type
        suspension.reason = reason
        suspension.suspended_by = request.user
        suspension.suspended_until = suspended_until
        suspension.is_active = True
        suspension.save()
        
        # Deactivate user account
        user.is_active = False
        user.save()

        AuditLog.objects.create(
            actor=request.user,
            target_user=user,
            action='user_suspended',
            message=f'{request.user.email} suspended {user.email} ({suspension_type})',
            metadata={'suspension_type': suspension_type, 'reason': reason, 'suspended_until': str(suspended_until) if suspended_until else None},
            ip_address=get_client_ip(request),
        )

        return redirect('dashboard:user_management')
class AdminUnsuspendUserView(LoginRequiredMixin, View):
    """Unsuspend a user."""
    
    @method_decorator(user_passes_test(requires_permission('access_user_management')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        if hasattr(user, 'suspension'):
            user.suspension.is_active = False
            user.suspension.save()

        user.is_active = True
        user.save()

        AuditLog.objects.create(
            actor=request.user,
            target_user=user,
            action='user_unsuspended',
            message=f'{request.user.email} lifted suspension for {user.email}',
            ip_address=get_client_ip(request),
        )

        return redirect('dashboard:user_management')

class AdminDisputeResolutionView(LoginRequiredMixin, TemplateView):
    """View and resolve escrow disputes."""
    template_name = 'admin/dispute_resolution.html'
    
    @method_decorator(user_passes_test(requires_permission('access_dispute_resolution')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter
        dispute_status = self.request.GET.get('status', 'disputed')
        
        # Get disputes
        disputes = EscrowTransaction.objects.filter(status='disputed').select_related(
            'order', 'buyer', 'order__seller'
        )
        
        if dispute_status == 'resolved':
            disputes = EscrowTransaction.objects.filter(
                status__in=['released', 'refunded']
            ).select_related('order', 'buyer', 'order__seller')
        
        context['disputes'] = disputes.order_by('-dispute_opened_at')[:100]
        context['dispute_status'] = dispute_status
        context['pending_count'] = EscrowTransaction.objects.filter(
            status='disputed'
        ).count()
        context['resolved_count'] = EscrowTransaction.objects.filter(
            status__in=['released', 'refunded']
        ).count()
        
        return context


class AdminResolveDisputeView(LoginRequiredMixin, View):
    """Resolve a dispute by releasing or refunding."""
    
    @method_decorator(user_passes_test(requires_permission('access_dispute_resolution')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    @transaction.atomic
    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
        
        action = request.POST.get('action')  # 'release' or 'refund'
        admin_notes = request.POST.get('admin_notes', '')
        
        if action == 'release':
            escrow.release_funds(actor=request.user, notes=admin_notes)
        elif action == 'refund':
            from wallets.models import award_wallet_credit
            award_wallet_credit(escrow.buyer, escrow.amount, 'Dispute Refund', escrow.id)
            escrow.status = 'refunded'
            escrow.resolved_by = request.user
            escrow.admin_resolution_notes = admin_notes
            escrow.refunded_at = timezone.now()
            escrow.save()
        
        return redirect('dashboard:disputes')


class AdminContentModerationView(LoginRequiredMixin, TemplateView):
    """Review and approve/reject content."""
    template_name = 'admin/content_moderation.html'
    
    @method_decorator(user_passes_test(requires_permission('access_content_moderation')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter
        status_filter = self.request.GET.get('status', 'pending')
        content_type = self.request.GET.get('type', '')
        
        # Get moderation queue
        items = ContentModerationQueue.objects.select_related('submitted_by', 'reviewed_by')
        
        if status_filter == 'pending':
            items = items.filter(status='pending')
        elif status_filter == 'approved':
            items = items.filter(status='approved')
        elif status_filter == 'rejected':
            items = items.filter(status='rejected')
        
        if content_type:
            items = items.filter(content_type=content_type)
        
        context['items'] = items.order_by('-created_at')[:100]
        context['status_filter'] = status_filter
        context['content_type'] = content_type
        context['pending_count'] = ContentModerationQueue.objects.filter(
            status='pending'
        ).count()
        context['content_types'] = ContentModerationQueue.ContentType.choices
        
        return context


class AdminModerateContentView(LoginRequiredMixin, View):
    """Approve or reject moderation item."""
    
    @method_decorator(user_passes_test(requires_permission('access_content_moderation')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request, item_id):
        item = get_object_or_404(ContentModerationQueue, id=item_id)
        
        action = request.POST.get('action')  # 'approve' or 'reject'
        reviewer_notes = request.POST.get('reviewer_notes', '')
        
        item.reviewed_by = request.user
        item.reviewed_at = timezone.now()
        item.reviewer_notes = reviewer_notes
        
        if action == 'approve':
            item.status = 'approved'
        elif action == 'reject':
            item.status = 'rejected'
            item.rejection_reason = request.POST.get('rejection_reason', '')
        
        item.save()
        
        return redirect('dashboard:moderation')


class AdminSettingsView(LoginRequiredMixin, TemplateView):
    """Manage system settings."""
    template_name = 'admin/settings.html'
    
    @method_decorator(user_passes_test(requires_permission('access_settings')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings'] = SystemSettings.objects.first() or SystemSettings.objects.create()
        return context


class AdminUpdateSettingsView(LoginRequiredMixin, View):
    """Update system settings."""
    
    @method_decorator(user_passes_test(requires_permission('access_settings')))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request):
        settings, created = SystemSettings.objects.get_or_create()
        
        # Update all fields
        settings.default_tax_rate = Decimal(request.POST.get('default_tax_rate', 16.0))
        settings.platform_commission_rate = Decimal(request.POST.get('platform_commission_rate', 10.0))
        settings.payment_processing_fee = Decimal(request.POST.get('payment_processing_fee', 2.5))
        settings.free_shipping_threshold = Decimal(request.POST.get('free_shipping_threshold', 10000.0))
        settings.base_shipping_cost = Decimal(request.POST.get('base_shipping_cost', 500.0))
        settings.auto_release_days = int(request.POST.get('auto_release_days', 7))
        settings.dispute_resolution_days = int(request.POST.get('dispute_resolution_days', 3))
        settings.maintenance_mode = request.POST.get('maintenance_mode') == 'on'
        settings.maintenance_message = request.POST.get('maintenance_message', '')
        settings.allow_new_sellers = request.POST.get('allow_new_sellers') == 'on'
        settings.require_seller_verification = request.POST.get('require_seller_verification') == 'on'
        settings.updated_by = request.user
        
        settings.save()
        
        return redirect('dashboard:settings')
