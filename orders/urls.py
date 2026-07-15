from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('', views.CartView.as_view(), name='cart'),
    path('add/', views.AddToCartView.as_view(), name='add_to_cart'),
    path('update/<uuid:item_id>/', views.UpdateCartView.as_view(), name='update_cart'),
    path('remove/<uuid:item_id>/', views.RemoveFromCartView.as_view(), name='remove_from_cart'),
    path('save/<uuid:item_id>/', views.SaveForLaterView.as_view(), name='save_for_later'),
    path('saved/move/<uuid:variant_id>/', views.MoveSavedToCartView.as_view(), name='move_saved_to_cart'),
    path('saved/remove/<uuid:variant_id>/', views.RemoveSavedFromListView.as_view(), name='remove_saved_item'),
    path('coupon/apply/', views.ApplyCouponView.as_view(), name='apply_coupon'),
    path('admin/coupons/', views.AdminCouponListView.as_view(), name='admin_coupons'),
    path('admin/coupons/add/', views.AdminCouponCreateView.as_view(), name='admin_coupon_add'),
    path('admin/coupons/<uuid:pk>/edit/', views.AdminCouponEditView.as_view(), name='admin_coupon_edit'),
    path('admin/orders/', views.AdminOrderListView.as_view(), name='admin_orders'),
    path('admin/bulk-actions/', views.AdminBulkOrderActionsView.as_view(), name='admin_bulk_actions'),
    path('admin/order/<str:order_number>/invoice/', views.AdminOrderInvoiceView.as_view(), name='admin_order_invoice'),
    path('admin/rma/', views.AdminRMAListView.as_view(), name='admin_rma'),
    path('admin/rma/<uuid:pk>/update/', views.AdminRMAUpdateView.as_view(), name='admin_rma_update'),
    path('admin/revenue/', views.AdminRevenueeDashboardView.as_view(), name='admin_revenue'),
    path('history/', views.OrderListView.as_view(), name='order_list'),
    path('history/<str:order_number>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('history/<str:order_number>/receipt/', views.OrderReceiptView.as_view(), name='order_receipt'),
    path('history/<str:order_number>/edit/', views.OrderEditView.as_view(), name='edit_order'),
    path('history/<str:order_number>/delete/', views.OrderDeleteView.as_view(), name='delete_order'),
]
