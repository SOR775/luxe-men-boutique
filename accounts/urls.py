"""
accounts/urls.py — Authentication URL Patterns
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('login-code/', views.EmailLoginCodeRequestView.as_view(), name='login_code_request'),
    path('login-code/verify/', views.EmailLoginCodeVerifyView.as_view(), name='login_code_verify'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Email Verification
    path('verify-email/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),

    # Password Reset
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/<str:token>/', views.ResetPasswordView.as_view(), name='reset_password'),

    # Profile & Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),

    # Address Book
    path('addresses/', views.AddressListView.as_view(), name='addresses'),
    path('addresses/add/', views.AddressCreateView.as_view(), name='address_add'),
    path('addresses/<uuid:pk>/delete/', views.AddressDeleteView.as_view(), name='address_delete'),

    # Wishlist
    path('wishlist/', views.WishlistView.as_view(), name='wishlist'),
    path('returns/', views.ReturnRequestsView.as_view(), name='returns'),
    path('support/', views.SupportHistoryView.as_view(), name='support_history'),

    # Login History
    path('login-history/', views.LoginHistoryView.as_view(), name='login_history'),
    # Admin user management
    path('admin/users/', views.AdminUserListView.as_view(), name='admin_users'),
    path('admin/users/<uuid:pk>/edit/', views.AdminUserEditView.as_view(), name='admin_user_edit'),
    path('admin/users/<uuid:pk>/password-reset/', views.AdminUserPasswordResetView.as_view(), name='admin_user_password_reset'),
    path('admin/audit/', views.AdminAuditLogListView.as_view(), name='admin_audit_log'),
    path('admin/audit/export/', views.AdminAuditLogExportCSVView.as_view(), name='admin_audit_export'),
    path('admin/audit/<uuid:pk>/', views.AdminAuditLogDetailView.as_view(), name='admin_audit_detail'),
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
]
