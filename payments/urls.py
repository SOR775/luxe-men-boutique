from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('select/<uuid:order_id>/', views.PaymentSelectView.as_view(), name='select'),
    path('wallet/<uuid:order_id>/', views.WalletPaymentView.as_view(), name='wallet_payment'),
    path('mpesa/push/<uuid:order_id>/', views.MpesaSTKPushView.as_view(), name='mpesa_push'),
    path('mpesa/query/<str:checkout_request_id>/', views.MpesaQueryView.as_view(), name='mpesa_query'),
    path('mpesa/callback/', views.MpesaCallbackView.as_view(), name='mpesa_callback'),
    path('success/<uuid:order_id>/', views.PaymentSuccessView.as_view(), name='success'),
    path('failed/<uuid:order_id>/', views.PaymentFailedView.as_view(), name='failed'),
]
