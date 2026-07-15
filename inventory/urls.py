from django.urls import path
app_name = 'inventory'
from . import views

urlpatterns = [
    path('admin/dashboard/', views.InventoryDashboardView.as_view(), name='admin_dashboard'),
    path('admin/sku-management/', views.InventorySkuManagementView.as_view(), name='admin_sku_management'),
    path('admin/stock-history/', views.InventoryStockHistoryView.as_view(), name='admin_stock_history'),
    path('admin/low-stock-alerts/', views.InventoryLowStockAlertView.as_view(), name='admin_low_stock_alerts'),
]

