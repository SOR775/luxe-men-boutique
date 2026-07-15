from django.urls import path

from . import views

app_name = 'wallets'

urlpatterns = [
    path('', views.WalletOverviewView.as_view(), name='overview'),
    path('transactions/', views.WalletTransactionsView.as_view(), name='transactions'),
    path('manage/', views.WalletManagementView.as_view(), name='manage'),
    path('top-up/', views.WalletTopUpView.as_view(), name='top_up'),
]
