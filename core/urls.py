"""
core/urls.py — Core URL patterns (homepage, static pages)
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('build-your-look/', views.BuildYourLookView.as_view(), name='build_your_look'),
    path('faq/', views.FAQView.as_view(), name='faq'),
    path('search/', views.SearchView.as_view(), name='search'),
    path('healthz/', views.healthz, name='healthz'),
    path('dark-mode/toggle/', views.toggle_dark_mode, name='toggle_dark_mode'),
    path('test-email/', views.test_email, name='test_email'),
]
