from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='list'),
    path('api/recent/', views.NotificationRecentAPIView.as_view(), name='api_recent'),
    path('api/mark-read/', views.NotificationMarkReadAPIView.as_view(), name='api_mark_read'),
    path('mark-read/<uuid:pk>/', views.NotificationReadView.as_view(), name='mark_read'),
    path('mark-all-read/', views.NotificationMarkAllReadView.as_view(), name='mark_all_read'),
]

