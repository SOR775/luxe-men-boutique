from django.urls import path

from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.marketing_home, name='home'),
    path('blog/', views.BlogListView.as_view(), name='blog_list'),
    path('blog/<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
    path('newsletter/subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),
]

