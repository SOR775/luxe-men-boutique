"""
escrow/urls.py
"""
from django.urls import path
from . import views

app_name = 'escrow'

urlpatterns = [
    # Buyer / Seller
    path('<uuid:escrow_id>/',           views.EscrowStatusView.as_view(),       name='status'),
    path('<uuid:escrow_id>/confirm/',    views.BuyerConfirmReceiptView.as_view(), name='confirm'),
    path('<uuid:escrow_id>/dispute/',    views.BuyerOpenDisputeView.as_view(),   name='dispute'),
    path('<uuid:escrow_id>/api/status/', views.EscrowStatusAPIView.as_view(),    name='api_status'),

    # Seller Dashboard
    path('sales/dashboard/', views.SellerSalesDashboardView.as_view(), name='seller_dashboard'),

    # Staff / Admin
    path('<uuid:escrow_id>/ship/',    views.SellerMarkShippedView.as_view(),   name='ship'),
    path('<uuid:escrow_id>/resolve/', views.AdminResolveDisputeView.as_view(), name='resolve'),
    path('<uuid:escrow_id>/release/', views.AdminReleaseEscrowView.as_view(), name='release'),
    path('dashboard/',                views.EscrowAdminDashboardView.as_view(), name='dashboard'),
    path('dashboard/auto-release/',    views.EscrowAutoReleaseView.as_view(), name='auto_release'),
]

