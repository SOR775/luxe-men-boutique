from django.urls import path
from django.views.generic import RedirectView

from marketing import views

app_name = 'blog'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='marketing:blog_list', permanent=False)),
    path('<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
]
