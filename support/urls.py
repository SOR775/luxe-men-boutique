from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('admin/tickets/', views.SupportTicketAdminListView.as_view(), name='ticket_admin_list'),
    path('tickets/', views.SupportTicketListView.as_view(), name='ticket_list'),
    path('tickets/<int:pk>/', views.SupportTicketDetailView.as_view(), name='ticket_detail'),
    path('tickets/<int:pk>/thread/', views.ticket_thread, name='ticket_thread'),
    path('tickets/<int:pk>/reply/', views.staff_reply, name='staff_reply'),
    path('tickets/<int:pk>/close/', views.close_ticket, name='close_ticket'),
    path('create/', views.create_support_ticket, name='create_ticket'),
    path('callback-requests/', views.CallbackRequestListView.as_view(), name='callback_requests'),
]

