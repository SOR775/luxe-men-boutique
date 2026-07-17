from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('admin/products/', views.AdminProductListView.as_view(), name='admin_products'),
    path('suggestions/', views.SearchSuggestionsView.as_view(), name='suggestions'),
    path('admin/categories/', views.AdminCategoryListView.as_view(), name='admin_categories'),
    path('admin/categories/add/', views.AdminCategoryCreateView.as_view(), name='admin_category_add'),
    path('admin/categories/<uuid:pk>/edit/', views.AdminCategoryEditView.as_view(), name='admin_category_edit'),

    path('', views.ShopView.as_view(), name='shop'),
    path('<slug:slug>/', views.ProductDetailView.as_view(), name='detail'),
    path('<uuid:pk>/wishlist/', views.ToggleWishlistView.as_view(), name='toggle_wishlist'),
    path('<uuid:pk>/review/', views.SubmitReviewView.as_view(), name='submit_review'),
    path('<uuid:pk>/review/<uuid:review_pk>/helpful/', views.HelpfulVoteView.as_view(), name='helpful_vote'),
]
