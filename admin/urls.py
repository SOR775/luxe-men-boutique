"""
admin/urls.py — Admin Dashboard URL Configuration
"""
from django.urls import path
from django.views.generic import RedirectView
from core import admin_views

app_name = 'dashboard'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='accounts:admin_dashboard', permanent=False), name='index'),
    # System Health
    path('system-health/', admin_views.AdminSystemHealthView.as_view(), name='system_health'),
    
    # User Management
    path('users/', admin_views.AdminUserManagementView.as_view(), name='user_management'),
    path('users/<uuid:user_id>/suspend/', admin_views.AdminSuspendUserView.as_view(), name='suspend_user'),
    path('users/<uuid:user_id>/unsuspend/', admin_views.AdminUnsuspendUserView.as_view(), name='unsuspend_user'),
    
    # Dispute Resolution
    path('disputes/', admin_views.AdminDisputeResolutionView.as_view(), name='disputes'),
    path('disputes/<uuid:escrow_id>/resolve/', admin_views.AdminResolveDisputeView.as_view(), name='resolve_dispute'),
    
    # Content Moderation
    path('moderation/', admin_views.AdminContentModerationView.as_view(), name='moderation'),
    path('moderation/<uuid:item_id>/review/', admin_views.AdminModerateContentView.as_view(), name='moderate_content'),
    
    # Settings
    path('settings/', admin_views.AdminSettingsView.as_view(), name='settings'),
    path('settings/update/', admin_views.AdminUpdateSettingsView.as_view(), name='update_settings'),
]
