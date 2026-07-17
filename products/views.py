"""
products/views.py — Shop Listing, Product Detail, Category Filtering
"""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from difflib import SequenceMatcher

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView
from django.db.models import Q, Min, Max, Avg, Count, Prefetch, F
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone

from notifications.models import Notification
from .models import Product, Category, Brand, Collection, ProductVariant, ProductImage
from .forms import CategoryForm


class ShopView(ListView):
    """
    Main shop listing page with filtering, sorting, and pagination.
    Supports HTMX partial responses for instant filter/sort updates and infinite scroll.
    """
    model = Product
    template_name = 'products/shop.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_template_names(self):
        """Return the partial template for HTMX requests, full template otherwise."""
        if self.request.headers.get('HX-Request'):
            return ['products/partials/shop_product_grid.html']
        return [self.template_name]

    def _search_matches(self, queryset, query):
        if not query:
            return queryset
        stripped = query.strip()
        words = [word for word in stripped.replace('-', ' ').split() if word]
        if not words:
            return queryset

        search_q = Q(name__icontains=stripped) | Q(description__icontains=stripped) | Q(brand__name__icontains=stripped)
        for word in words:
            search_q |= Q(name__icontains=word) | Q(description__icontains=word) | Q(brand__name__icontains=word)

        queryset = queryset.filter(search_q).distinct()
        if queryset.exists():
            return queryset

        normalized_query = ''.join(ch.lower() for ch in stripped if ch.isalnum())
        fallback_matches = []
        for product in Product.objects.filter(visibility=Product.Visibility.PUBLISHED).only('name', 'slug', 'description', 'brand_id'):
            haystack = ' '.join(filter(None, [product.name, product.description, getattr(product.brand, 'name', '')])).lower()
            normalized_haystack = ''.join(ch for ch in haystack if ch.isalnum())
            if normalized_query and normalized_haystack and SequenceMatcher(None, normalized_query, normalized_haystack).ratio() >= 0.62:
                fallback_matches.append(product.pk)

        if fallback_matches:
            return queryset.model.objects.filter(pk__in=fallback_matches)
        return queryset

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Avg
        from .models import WishlistItem
        qs = Product.objects.filter(
            visibility=Product.Visibility.PUBLISHED
        ).select_related('brand', 'category').prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
        ).annotate(avg_rating=Avg('reviews__rating'))

        if self.request.user.is_authenticated:
            qs = qs.annotate(
                in_wishlist=Exists(
                    WishlistItem.objects.filter(user=self.request.user, product=OuterRef('pk'))
                )
            )

        # Filter by category slug
        category_slug = self.request.GET.get('category')
        if category_slug:
            qs = qs.filter(
                Q(category__slug=category_slug) | Q(category__parent__slug=category_slug)
            )

        # Filter by brand slug
        brand_slug = self.request.GET.get('brand')
        if brand_slug:
            qs = qs.filter(brand__slug=brand_slug)

        # Filter by collection slug
        collection_slug = self.request.GET.get('collection')
        if collection_slug:
            qs = qs.filter(collection__slug=collection_slug)

        # Multi-select filters from the product variants
        size_values = self.request.GET.getlist('size')
        if size_values:
            qs = qs.filter(variants__size__in=size_values, variants__is_active=True).distinct()

        color_values = self.request.GET.getlist('color')
        if color_values:
            qs = qs.filter(variants__color__in=color_values, variants__is_active=True).distinct()

        material_values = self.request.GET.getlist('material')
        if material_values:
            qs = qs.filter(variants__material__in=material_values, variants__is_active=True).distinct()

        # Availability filter
        if self.request.GET.getlist('in_stock'):
            qs = qs.filter(variants__stock_levels__quantity__gt=0).distinct()

        # Discount / sale filter
        if self.request.GET.getlist('discount'):
            qs = qs.filter(compare_at_price__isnull=False, compare_at_price__gt=F('base_price'))

        # New arrivals filter based on created within 30 days
        if self.request.GET.getlist('new_arrivals'):
            qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=30))

        # Rating filter
        rating_values = self.request.GET.getlist('rating')
        if rating_values:
            min_rating = min(int(value) for value in rating_values if value.isdigit())
            qs = qs.annotate(avg_rating=Avg('reviews__rating')).filter(avg_rating__gte=min_rating)

        # Price range filter
        min_price = self.request.GET.get('min_price')
        max_price = self.request.GET.get('max_price')
        if min_price:
            qs = qs.filter(base_price__gte=min_price)
        if max_price:
            qs = qs.filter(base_price__lte=max_price)

        # Text search
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = self._search_matches(qs, q)

        # Special filters
        if self.request.GET.get('featured'):
            qs = qs.filter(is_featured=True)
        if self.request.GET.get('trending'):
            qs = qs.filter(is_trending=True)

        # Sorting
        sort = self.request.GET.get('sort', 'newest')
        sort_map = {
            'newest': '-created_at',
            'oldest': 'created_at',
            'price_asc': 'base_price',
            'price_desc': '-base_price',
            'name_asc': 'name',
            'popularity': '-created_at',
            'rating': '-avg_rating',
            'best_selling': '-created_at',
        }
        qs = qs.order_by(sort_map.get(sort, '-created_at'))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(is_active=True, parent=None).prefetch_related('subcategories')
        context['brands'] = Brand.objects.filter(is_active=True)
        context['collections'] = Collection.objects.filter(is_active=True)
        context['current_sort'] = self.request.GET.get('sort', 'newest')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_brand'] = self.request.GET.get('brand', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['current_sizes'] = self.request.GET.getlist('size')
        context['current_colors'] = self.request.GET.getlist('color')
        context['current_materials'] = self.request.GET.getlist('material')
        context['current_ratings'] = self.request.GET.getlist('rating')
        context['has_stock_filter'] = bool(self.request.GET.getlist('in_stock'))
        context['has_discount_filter'] = bool(self.request.GET.getlist('discount'))
        context['has_new_arrivals_filter'] = bool(self.request.GET.getlist('new_arrivals'))
        context['product_sizes'] = ProductVariant.objects.filter(is_active=True).exclude(size='').values_list('size', flat=True).distinct().order_by('size')
        context['product_colors'] = ProductVariant.objects.filter(is_active=True).exclude(color='').values_list('color', flat=True).distinct().order_by('color')
        context['product_materials'] = ProductVariant.objects.filter(is_active=True).exclude(material='').values_list('material', flat=True).distinct().order_by('material')
        context['total_count'] = self.get_queryset().count()

        featured_products = list(
            Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED,
                is_featured=True,
            ).select_related('brand', 'category').prefetch_related(
                Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
            ).order_by('-created_at')[:4]
        )
        context['featured_products'] = featured_products
        return context


class ProductDetailView(DetailView):
    """
    Full product detail page with variant selection.
    """
    model = Product
    template_name = 'products/product_detail.html'
    context_object_name = 'product'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Product.objects.filter(
            visibility=Product.Visibility.PUBLISHED
        ).select_related('brand', 'category', 'collection').prefetch_related(
            'images', 'variants'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # Group variants by attribute for the selector UI
        variants = product.variants.filter(is_active=True)
        context['sizes'] = sorted(set(v.size for v in variants if v.size))
        context['colors'] = sorted(set(v.color for v in variants if v.color))
        variant_rows = list(variants.values(
            'id', 'sku', 'size', 'color', 'material', 'price_adjustment'
        ))
        context['variants_data'] = json.dumps([
            {
                'id': str(row['id']),
                'sku': row['sku'],
                'size': row['size'],
                'color': row['color'],
                'material': row['material'],
                'price_adjustment': float(row['price_adjustment']),
            }
            for row in variant_rows
        ])

        # "You Might Also Like" - same category, annotated with avg rating
        from django.db.models import Avg
        context['related_products'] = Product.objects.filter(
            visibility=Product.Visibility.PUBLISHED,
            category=product.category,
        ).exclude(pk=product.pk).annotate(
            avg_rating=Avg('reviews__rating')
        ).prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
        ).order_by('-is_featured', '-created_at')[:4]

        # "Complete the Look" - cross-category recommendations (same brand / different category)
        context['complete_look'] = Product.objects.filter(
            visibility=Product.Visibility.PUBLISHED,
            brand=product.brand,
        ).exclude(pk=product.pk).exclude(
            category=product.category
        ).prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
        ).order_by('?')[:4]

        context['product_details'] = {
            'size_chart': product.size_chart or None,
            'fabric_info': product.fabric_info or None,
            'care_instructions': product.care_instructions or None,
            'model_height': product.model_height or None,
            'model_size_worn': product.model_size_worn or None,
        }

        # Wishlist status
        context['in_wishlist'] = False
        if self.request.user.is_authenticated:
            from .models import WishlistItem
            context['in_wishlist'] = WishlistItem.objects.filter(user=self.request.user, product=product).exists()

        # Stock urgency messaging
        context['stock_message'] = None
        # aggregate inventory per variant
        variant_inventory = {}
        total_available = 0
        low_stock_any = False
        for v in variants:
            qty = 0
            low = False
            try:
                stocks = v.stock_levels.all()
                for s in stocks:
                    qty += s.quantity
                    if s.is_low_stock:
                        low = True
            except Exception:
                stocks = []
            variant_inventory[str(v.id)] = {
                'quantity': qty,
                'low_stock': low,
            }
            total_available += qty
            if low:
                low_stock_any = True

        context['variant_inventory'] = variant_inventory

        # size and color aggregate inventory (min qty across matching variants)
        size_inventory = {}
        color_inventory = {}
        for v in variants:
            vid = str(v.id)
            size = v.size or ''
            color = v.color or ''
            q = variant_inventory.get(vid, {}).get('quantity', 0)
            # size
            if size:
                if size in size_inventory:
                    size_inventory[size] = min(size_inventory[size], q) if q > 0 else 0
                else:
                    size_inventory[size] = q
            # color
            if color:
                if color in color_inventory:
                    color_inventory[color] = min(color_inventory[color], q) if q > 0 else 0
                else:
                    color_inventory[color] = q

        context['size_inventory'] = size_inventory
        context['color_inventory'] = color_inventory

        # JSON-serialized versions for safe JS injection in template
        try:
            context['variant_inventory_json'] = json.dumps(variant_inventory)
            context['size_inventory_json'] = json.dumps(size_inventory)
            context['color_inventory_json'] = json.dumps(color_inventory)
        except Exception:
            context['variant_inventory_json'] = '{}'
            context['size_inventory_json'] = '{}'
            context['color_inventory_json'] = '{}'

        if total_available == 0:
            context['stock_message'] = 'Currently out of stock.'
        elif low_stock_any:
            # show the lowest available quantity across variants
            min_qty = min((d['quantity'] for d in variant_inventory.values() if d['quantity'] > 0), default=0)
            if min_qty > 0:
                context['stock_message'] = f'Only {min_qty} left in some sizes — order soon.'
            else:
                context['stock_message'] = 'Limited stock available — order soon.'
        else:
            context['stock_message'] = 'In stock and ready to ship.'

        # Estimated delivery (simple heuristic)
        if total_available > 0:
            context['estimated_delivery'] = 'Estimated delivery: 2–5 business days'
        else:
            context['estimated_delivery'] = 'Estimated delivery: 10–14 business days (pre-order/backorder)'

        # Product media: gallery, 360 view, video, manual
        gallery = list(product.images.order_by('order').all())
        context['gallery_images'] = [img.image.url for img in gallery if img.image and getattr(img.image, 'name', None)]
        try:
            context['gallery_images_json'] = json.dumps(context['gallery_images'])
        except Exception:
            context['gallery_images_json'] = '[]'

        img360 = next((img for img in gallery if getattr(img, 'image_360', None) and getattr(img.image_360, 'name', None)), None)
        context['image_360_url'] = img360.image_360.url if img360 and getattr(img360.image_360, 'name', None) else None

        vid = next((img for img in gallery if getattr(img, 'video', None) and getattr(img.video, 'name', None)), None)
        context['video_url'] = vid.video.url if vid and getattr(vid.video, 'name', None) else None

        # digital manual: check for file under MEDIA_ROOT/products/manuals/{slug}.pdf
        try:
            import os
            from django.conf import settings
            manual_path = os.path.join(settings.MEDIA_ROOT or '', 'products', 'manuals', f'{product.slug}.pdf')
            if os.path.exists(manual_path):
                context['manual_url'] = f"{settings.MEDIA_URL}products/manuals/{product.slug}.pdf"
            else:
                context['manual_url'] = None
        except Exception:
            context['manual_url'] = None

        # Bundles: show other items from same collection as potential bundles
        context['bundled_products'] = []
        try:
            if product.collection:
                context['bundled_products'] = list(
                    Product.objects.filter(collection=product.collection, visibility=Product.Visibility.PUBLISHED)
                    .exclude(pk=product.pk).prefetch_related(
                        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
                    )[:3]
                )
        except Exception:
            context['bundled_products'] = []

        # Recently viewed products from session
        viewed_ids = self.request.session.get('recently_viewed', []) or []
        if isinstance(viewed_ids, str):
            viewed_ids = [viewed_ids]
        viewed_ids = [str(v) for v in viewed_ids if str(v) != str(product.pk)]
        viewed_ids.insert(0, str(product.pk))
        viewed_ids = viewed_ids[:6]
        self.request.session['recently_viewed'] = viewed_ids

        if isinstance(viewed_ids, str):
            viewed_ids = [viewed_ids]
        viewed_ids = [vid for vid in viewed_ids if str(vid) != str(product.pk)]
        recently_viewed = []
        if viewed_ids:
            recently_viewed = list(
                Product.objects.filter(
                    visibility=Product.Visibility.PUBLISHED,
                    pk__in=viewed_ids,
                ).prefetch_related(
                    Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images')
                ).order_by('name')[:4]
            )
        context['recently_viewed'] = recently_viewed
        context['has_recently_viewed'] = bool(recently_viewed)

        # Reviews & ratings
        from django.db.models import Avg, Count
        review_stats = product.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
        review_filter = self.request.GET.get('review_filter', 'all')
        reviews = product.reviews.select_related('user').all()
        if review_filter == 'positive':
            reviews = reviews.filter(rating__gte=4)
        elif review_filter == 'critical':
            reviews = reviews.filter(rating__lte=2)
        elif review_filter == 'verified':
            reviews = reviews.filter(is_verified_purchase=True)

        context['reviews'] = reviews
        context['avg_rating'] = round(review_stats['avg'] or 0, 1)
        context['review_count'] = review_stats['count']
        context['rating_range'] = range(1, 6)
        context['review_filter'] = review_filter
        context['review_breakdown'] = {
            'five': product.reviews.filter(rating=5).count(),
            'four': product.reviews.filter(rating=4).count(),
            'three': product.reviews.filter(rating=3).count(),
            'two': product.reviews.filter(rating=2).count(),
            'one': product.reviews.filter(rating=1).count(),
        }
        context['fit_feedback_summary'] = {
            'true_to_size': product.reviews.filter(fit_feedback='true_to_size').count(),
            'runs_small': product.reviews.filter(fit_feedback='runs_small').count(),
            'runs_large': product.reviews.filter(fit_feedback='runs_large').count(),
        }

        if context['review_count']:
            if context['avg_rating'] >= 4.5:
                context['social_proof_message'] = f"Rated {context['avg_rating']:.1f}/5 by {context['review_count']} happy customer{'s' if context['review_count'] != 1 else ''}."
            else:
                context['social_proof_message'] = f"Loved by {context['review_count']} customer{'s' if context['review_count'] != 1 else ''} and counting."
        else:
            context['social_proof_message'] = 'Join the first customers to share their experience.'

        # Current user's own review (for pre-filling edit form)
        context['user_review'] = None
        if self.request.user.is_authenticated:
            from .models import ProductReview
            context['user_review'] = ProductReview.objects.filter(
                user=self.request.user, product=product
            ).first()

        return context


class AdminProductListView(LoginRequiredMixin, TemplateView):
    template_name = 'products/admin/product_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(
            visibility=Product.Visibility.PUBLISHED
        ).select_related('brand', 'category').prefetch_related('images').order_by('-created_at')
        return context


class AdminCategoryListView(LoginRequiredMixin, TemplateView):
    template_name = 'products/admin/category_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.order_by('name')
        return context


class AdminCategoryCreateView(LoginRequiredMixin, View):
    template_name = 'products/admin/category_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = CategoryForm()
        return render(request, self.template_name, {'form': form, 'is_edit': False})

    def post(self, request):
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category created successfully.')
            return redirect('products:admin_categories')
        return render(request, self.template_name, {'form': form, 'is_edit': False})


class AdminCategoryEditView(LoginRequiredMixin, View):
    template_name = 'products/admin/category_form.html'

    def dispatch(self, request, pk, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('accounts:dashboard')
        self.category = get_object_or_404(Category, pk=pk)
        return super().dispatch(request, pk, *args, **kwargs)

    def get(self, request, pk):
        form = CategoryForm(instance=self.category)
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'category': self.category})

    def post(self, request, pk):
        form = CategoryForm(request.POST, request.FILES, instance=self.category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully.')
            return redirect('products:admin_categories')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'category': self.category})


class SearchSuggestionsView(View):
    def get(self, request, *args, **kwargs):
        q = (request.GET.get('q') or '').strip()
        products = Product.objects.filter(visibility=Product.Visibility.PUBLISHED)
        if q:
            products = ShopView()._search_matches(products, q)
        suggestions = [
            {
                'name': product.name,
                'slug': product.slug,
                'url': product.get_absolute_url(),
                'brand': product.brand.name if product.brand else '',
            }
            for product in products[:6].select_related('brand')
        ]
        return JsonResponse(suggestions, safe=False)


class ToggleWishlistView(LoginRequiredMixin, View):
    """Toggle a product in the user's wishlist via AJAX."""
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        from .models import WishlistItem
        item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
            return JsonResponse({'status': 'removed'})

        try:
            Notification.create(
                user=request.user,
                title=f'{product.name} added to your wishlist',
                message='We will notify you if this item is back in stock or drops in price.',
                target_url=product.get_absolute_url() if hasattr(product, 'get_absolute_url') else f'/products/{product.slug}/',
                level=Notification.Level.INFO,
            )
        except Exception:
            pass

        return JsonResponse({'status': 'added'})


from django.contrib import messages
from django.shortcuts import redirect


class HelpfulVoteView(LoginRequiredMixin, View):
    """Mark a product review as helpful once per session."""
    def post(self, request, pk, review_pk):
        product = get_object_or_404(Product, pk=pk)
        from .models import ProductReview

        review = get_object_or_404(ProductReview, pk=review_pk, product=product)
        voted_review_ids = request.session.get('helpful_review_votes', []) or []
        if isinstance(voted_review_ids, str):
            voted_review_ids = [voted_review_ids]
        voted_review_ids = [str(v) for v in voted_review_ids if str(v)]

        if str(review.pk) in voted_review_ids:
            messages.info(request, 'You already marked this review as helpful.')
        else:
            ProductReview.objects.filter(pk=review.pk).update(helpful_votes=F('helpful_votes') + 1)
            voted_review_ids.insert(0, str(review.pk))
            request.session['helpful_review_votes'] = voted_review_ids[:100]
            request.session.modified = True
            messages.success(request, 'Thanks for marking this review as helpful.')

        return redirect('products:detail', slug=product.slug)


class SubmitReviewView(LoginRequiredMixin, View):
    """Submit a review for a product."""
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()
        
        if not rating or not rating.isdigit() or not (1 <= int(rating) <= 5):
            messages.error(request, 'Please provide a valid 1-5 star rating.')
            return redirect('products:detail', slug=product.slug)

        from .models import ProductReview
        fit_feedback = request.POST.get('fit_feedback', '').strip()
        is_verified_purchase = bool(request.POST.get('verified_purchase'))
        review, created = ProductReview.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={
                'rating': int(rating),
                'comment': comment,
                'fit_feedback': fit_feedback,
                'is_verified_purchase': is_verified_purchase,
            }
        )
        
        if created:
            messages.success(request, 'Thank you! Your review has been published.')
        else:
            messages.success(request, 'Your review has been updated.')
            
        return redirect('products:detail', slug=product.slug)

