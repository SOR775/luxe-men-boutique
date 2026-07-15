from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from inventory.models import Stock, Warehouse
from .models import Product, ProductImage, ProductVariant, ProductReview
from .views import ProductDetailView, ShopView


class ShopFilterTests(TestCase):
    def test_shop_view_supports_multi_select_filters_and_availability(self):
        product = Product.objects.create(
            name='Tailored Blazer',
            slug='tailored-blazer',
            base_price=120,
            compare_at_price=150,
            visibility=Product.Visibility.PUBLISHED,
            created_at='2026-01-01T00:00:00Z',
        )
        variant = ProductVariant.objects.create(
            product=product,
            sku='TB-001',
            size='M',
            color='Blue',
            material='Cotton',
            is_active=True,
        )
        warehouse = Warehouse.objects.create(name='Main Warehouse')
        Stock.objects.create(variant=variant, warehouse=warehouse, quantity=3, low_stock_threshold=2)

        ProductReview.objects.create(
            user=get_user_model().objects.create_user(username='reviewer', email='reviewer@example.com', password='secret123'),
            product=product,
            rating=5,
            comment='Great fit',
        )

        request = RequestFactory().get('/shop/', {
            'size': ['M'],
            'color': ['Blue'],
            'material': ['Cotton'],
            'in_stock': ['1'],
            'discount': ['1'],
            'new_arrivals': ['1'],
            'rating': ['4'],
        })
        request.user = AnonymousUser()

        view = ShopView()
        view.request = request
        queryset = view.get_queryset()

        self.assertEqual(list(queryset), [product])


class ProductSearchTests(TestCase):
    def test_shop_search_supports_typo_tolerant_matches(self):
        product = Product.objects.create(
            name='Tailored Blazer',
            slug='tailored-blazer',
            base_price=120,
            visibility=Product.Visibility.PUBLISHED,
        )

        request = RequestFactory().get('/shop/', {'q': 'tailord blazer'})
        request.user = AnonymousUser()

        view = ShopView()
        view.request = request
        queryset = view.get_queryset()

        self.assertIn(product, queryset)

    def test_search_suggestions_endpoint_returns_matches(self):
        product = Product.objects.create(
            name='Tailored Blazer',
            slug='tailored-blazer',
            base_price=120,
            visibility=Product.Visibility.PUBLISHED,
        )

        response = self.client.get(reverse('products:suggestions'), {'q': 'tailo'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item['slug'] == product.slug for item in payload))


class ProductDetailCartTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Test Shirt',
            slug='test-shirt',
            base_price=50,
            visibility=Product.Visibility.PUBLISHED,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='TEST-1',
            size='M',
            color='Blue',
            price_adjustment=0,
            is_active=True,
        )

    def test_product_detail_page_renders_with_variants(self):
        response = self.client.get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        self.assertEqual(response.status_code, 200)

    def test_product_detail_renders_valid_json_variants(self):
        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('variants_data', context)
        self.assertIn(str(self.variant.id), context['variants_data'])

    def test_product_detail_renders_cart_form_with_variant_hidden_input(self):
        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('variants_data', context)
        self.assertIn('product', context)

    def test_product_detail_includes_social_proof_message(self):
        user = get_user_model().objects.create_user(username='reviewer', email='reviewer@example.com', password='secret123')
        ProductReview.objects.create(
            user=user,
            product=self.product,
            rating=5,
            comment='Excellent fit',
        )

        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('social_proof_message', context)
        self.assertIn('Rated', context['social_proof_message'])

    def test_product_detail_builds_fit_feedback_summary(self):
        user = get_user_model().objects.create_user(username='reviewer', email='reviewer@example.com', password='secret123')
        ProductReview.objects.create(
            user=user,
            product=self.product,
            rating=5,
            comment='Excellent fit',
            fit_feedback='true_to_size',
        )

        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('fit_feedback_summary', context)
        self.assertEqual(context['fit_feedback_summary']['true_to_size'], 1)

    def test_product_detail_includes_stock_urgency_message(self):
        warehouse = Warehouse.objects.create(name='Main Warehouse')
        Stock.objects.create(variant=self.variant, warehouse=warehouse, quantity=3, low_stock_threshold=5)

        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('stock_message', context)
        self.assertIn('Only 3 left', context['stock_message'])

    def test_product_detail_includes_recently_viewed_products_from_session(self):
        other_product = Product.objects.create(
            name='Tailored Jacket',
            slug='tailored-jacket',
            base_price=89.99,
            visibility=Product.Visibility.PUBLISHED,
        )
        ProductVariant.objects.create(
            product=other_product,
            sku='TJ-001',
            size='L',
            color='Navy',
            price_adjustment=0,
            is_active=True,
        )

        session = self.client.session
        session['recently_viewed'] = [str(other_product.id)]
        session.save()

        factory = RequestFactory()
        request = factory.get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.session = session
        request.user = AnonymousUser()

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIn('recently_viewed', context)
        self.assertEqual([item.id for item in context['recently_viewed']], [other_product.id])

    def test_product_detail_omits_fake_media_urls_when_media_fields_are_empty(self):
        ProductImage.objects.create(
            product=self.product,
            image='products/images/test.jpg',
            alt_text='Test image',
            is_primary=True,
        )

        request = RequestFactory().get(reverse('products:detail', kwargs={'slug': self.product.slug}))
        request.user = AnonymousUser()
        request.session = self.client.session

        view = ProductDetailView()
        view.request = request
        view.kwargs = {'slug': self.product.slug}
        view.object = self.product
        context = view.get_context_data(object=self.product)

        self.assertIsNone(context['image_360_url'])
        self.assertIsNone(context['video_url'])
        self.assertIsNone(context['manual_url'])
