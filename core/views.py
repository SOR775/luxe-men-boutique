"""
core/views.py — Core Views (Homepage, Search, Static Pages)
"""
from django.shortcuts import render, redirect
from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.db.models import Q
from django.core.paginator import Paginator


class HomeView(TemplateView):
    """
    Luxury homepage view — assembles all featured content sections.
    """
    template_name = 'core/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            from products.models import Product, Category, Collection, ProductImage
            from django.db.models import Prefetch

            primary_images_prefetch = Prefetch(
                'images',
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr='primary_images'
            )

            # New Arrivals (latest 8 published products)
            context['new_arrivals'] = Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED
            ).select_related('brand').prefetch_related(
                primary_images_prefetch
            ).order_by('-created_at')[:8]

            # Featured Products
            context['featured_products'] = Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED,
                is_featured=True
            ).select_related('brand').prefetch_related(
                primary_images_prefetch
            )[:8]

            # Trending Products
            context['trending_products'] = Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED,
                is_trending=True
            ).select_related('brand').prefetch_related(
                primary_images_prefetch
            )[:6]

            # Categories (top-level with subcategories)
            context['categories'] = Category.objects.filter(
                is_active=True, parent=None
            ).prefetch_related('subcategories')[:6]

            # Collections
            context['collections'] = Collection.objects.filter(
                is_active=True
            ).order_by('-start_date')[:3]

        except Exception:
            context['featured_products'] = []
            context['new_arrivals'] = []
            context['trending_products'] = []
            context['categories'] = []
            context['collections'] = []

        context['blog_posts'] = []
        context['faqs'] = []
        context['reviews'] = []

        return context


class SearchView(View):
    """
    Smart search across products, categories, and brands.
    Supports voice search via query parameter.
    """
    template_name = 'core/search.html'

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        results = []

        if query and len(query) >= 2:
            from products.models import Product
            results = Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED
            ).filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(brand__name__icontains=query) |
                Q(category__name__icontains=query) |
                Q(variants__sku__icontains=query)
            ).select_related('brand', 'category').prefetch_related(
                'images', 'variants'
            ).distinct()

        paginator = Paginator(results, 24)
        page = request.GET.get('page', 1)
        page_obj = paginator.get_page(page)

        # AJAX / HTMX partial response
        if request.headers.get('HX-Request'):
            return render(request, 'partials/search_results.html', {
                'results': page_obj,
                'query': query,
            })

        return render(request, self.template_name, {
            'results': page_obj,
            'query': query,
            'total': paginator.count,
            'popular_terms': ['Suits', 'Jackets', 'Shirts', 'Trousers', 'Sneakers', 'Accessories'],
        })


class AboutView(TemplateView):
    template_name = 'core/about.html'


class BuildYourLookView(View):
    template_name = 'core/build_your_look.html'

    STYLE_CHOICES = [
        ('minimal', 'Minimal & Refined'),
        ('bold', 'Bold Statement'),
        ('classic', 'Classic Tailoring'),
        ('smart_casual', 'Smart Casual'),
        ('formal', 'Formal Affair'),
    ]

    OCCASION_CHOICES = [
        ('date', 'Date Night'),
        ('work', 'Office & Meetings'),
        ('weekend', 'Weekend & Travel'),
        ('formal', 'Black Tie & Events'),
        ('lounge', 'Elevated Leisure'),
    ]

    BUDGET_CHOICES = [
        ('low', 'Under 5,000'),
        ('medium', '5,000 - 15,000'),
        ('high', '15,000+'),
    ]

    RECOMMENDATION_MAP = {
        'minimal': ['minimal', 'essential', 'clean', 'tailored', 'slim'],
        'bold': ['bold', 'statement', 'contrast', 'pattern', 'texture'],
        'classic': ['classic', 'timeless', 'heritage', 'tailored', 'structured'],
        'smart_casual': ['smart', 'casual', 'relaxed', 'layer', 'chic'],
        'formal': ['tuxedo', 'suit', 'dress', 'evening', 'lapel'],
        'date': ['shirt', 'jacket', 'suit', 'leather', 'silk'],
        'work': ['blazer', 'shirt', 'trousers', 'knit', 'tailor'],
        'weekend': ['denim', 'jacket', 'sweater', 'knit', 'casual'],
        'lounge': ['knit', 'jersey', 'relaxed', 'soft', 'premium'],
    }

    PRICE_TIERS = {
        'low': (0, 5000),
        'medium': (5000, 15000),
        'high': (15000, 99999999),
    }

    def get(self, request):
        return render(request, self.template_name, {
            'style_choices': self.STYLE_CHOICES,
            'occasion_choices': self.OCCASION_CHOICES,
            'budget_choices': self.BUDGET_CHOICES,
            'results': None,
            'summary': None,
            'selected_style': 'minimal',
            'selected_occasion': 'work',
            'selected_budget': 'medium',
        })

    def post(self, request):
        style = request.POST.get('style', 'minimal')
        occasion = request.POST.get('occasion', 'work')
        budget = request.POST.get('budget', 'medium')

        results = self.get_recommendations(style, occasion, budget)
        summary = {
            'style': dict(self.STYLE_CHOICES).get(style, 'Minimal & Refined'),
            'occasion': dict(self.OCCASION_CHOICES).get(occasion, 'Office & Meetings'),
            'budget': dict(self.BUDGET_CHOICES).get(budget, '5,000 - 15,000'),
        }

        return render(request, self.template_name, {
            'style_choices': self.STYLE_CHOICES,
            'occasion_choices': self.OCCASION_CHOICES,
            'budget_choices': self.BUDGET_CHOICES,
            'results': results,
            'summary': summary,
            'selected_style': style,
            'selected_occasion': occasion,
            'selected_budget': budget,
        })

    def get_recommendations(self, style, occasion, budget):
        try:
            from products.models import Product, ProductImage
            from django.db.models import Prefetch

            primary_images_prefetch = Prefetch(
                'images',
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr='primary_images'
            )

            terms = []
            style_terms = self.RECOMMENDATION_MAP.get(style, [])
            occasion_terms = self.RECOMMENDATION_MAP.get(occasion, [])
            terms.extend(style_terms)
            terms.extend(occasion_terms)

            query = None
            from django.db.models import Q
            for term in terms:
                q = Q(name__icontains=term) | Q(description__icontains=term) | Q(category__name__icontains=term) | Q(brand__name__icontains=term) | Q(collection__name__icontains=term)
                query = q if query is None else query | q

            queryset = Product.objects.filter(
                visibility=Product.Visibility.PUBLISHED,
            ).select_related('brand', 'category', 'collection').prefetch_related(primary_images_prefetch)

            if query is not None:
                queryset = queryset.filter(query)

            min_price, max_price = self.PRICE_TIERS.get(budget, (5000, 15000))
            if min_price is not None:
                queryset = queryset.filter(base_price__gte=min_price)
            if max_price is not None and max_price < 99999999:
                queryset = queryset.filter(base_price__lte=max_price)

            results = queryset.order_by('-is_featured', '-is_trending', '-created_at')[:8]
            if not results:
                results = Product.objects.filter(
                    visibility=Product.Visibility.PUBLISHED,
                ).select_related('brand', 'category').prefetch_related(primary_images_prefetch).order_by('-is_featured', '-is_trending', '-created_at')[:6]

            return results
        except Exception:
            return []


class ContactView(View):
    template_name = 'core/contact.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '')

        if name and email and message:
            # Save as support ticket and contact message record
            try:
                from support.models import ContactMessage, SupportTicket

                ContactMessage.objects.create(
                    name=name,
                    email=email,
                    subject=subject,
                    message=message,
                    user=request.user if request.user.is_authenticated else None,
                )

                SupportTicket.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    email=email,
                    subject=subject or 'General support request',
                    description=message,
                )
            except Exception:
                pass

            if request.headers.get('HX-Request'):
                return render(request, 'partials/contact_success.html')
            return redirect('core:contact')

        return render(request, self.template_name, {
            'error': 'All fields are required.',
            'name': name,
            'email': email,
            'subject': subject,
            'message': message,
        })

        return render(request, self.template_name, {'error': 'All fields are required.'})


class FAQView(TemplateView):
    template_name = 'core/faq.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            from support.models import FAQ, FAQCategory
            context['faq_categories'] = FAQCategory.objects.prefetch_related(
                'faqs'
            ).filter(faqs__is_active=True).distinct()
        except Exception:
            context['faq_categories'] = []
        return context


def toggle_dark_mode(request):
    """Toggle dark/light mode preference stored in session."""
    current = request.session.get('dark_mode', False)
    request.session['dark_mode'] = not current
    return JsonResponse({'dark_mode': not current})
