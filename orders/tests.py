from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.template.loader import render_to_string

from products.models import Category, Product, ProductVariant
from .models import Cart, CartItem
from .views import CartView, get_cart_promo_context, get_cart_recommendations, get_cart_financial_context


class CartPromoContextTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shirts', slug='shirts')
        self.product = Product.objects.create(
            name='Classic Shirt',
            slug='classic-shirt',
            description='A test shirt',
            category=self.category,
            base_price=50,
            visibility=Product.Visibility.PUBLISHED,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='CS-001',
            size='M',
            color='Black',
            price_adjustment=0,
            is_active=True,
        )

    def test_cart_view_includes_free_shipping_promo_context(self):
        cart = Cart.objects.create(session_key=self.client.session.session_key)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        cart = Cart.objects.get(session_key=self.client.session.session_key)
        promo_context = get_cart_promo_context(cart)

        self.assertIn('promo_message', promo_context)
        self.assertIn('free_shipping_remaining', promo_context)
        self.assertEqual(promo_context['free_shipping_remaining'], Decimal('4950.00'))

    def test_cart_recommendations_include_complementary_products_from_same_category(self):
        cart = Cart.objects.create(session_key=self.client.session.session_key)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        complementary = Product.objects.create(
            name='Matching Belt',
            slug='matching-belt',
            description='A test belt',
            category=self.category,
            base_price=35,
            visibility=Product.Visibility.PUBLISHED,
        )
        ProductVariant.objects.create(
            product=complementary,
            sku='MB-001',
            size='One Size',
            color='Black',
            price_adjustment=0,
            is_active=True,
        )

        recommendations = get_cart_recommendations(cart)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].name, 'Matching Belt')


class CartFinancialContextTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shirts', slug='shirts')
        self.product = Product.objects.create(
            name='Classic Shirt',
            slug='classic-shirt',
            description='A test shirt',
            category=self.category,
            base_price=50,
            visibility=Product.Visibility.PUBLISHED,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='CS-101',
            size='M',
            color='Black',
            price_adjustment=0,
            is_active=True,
        )

    def test_financial_context_includes_shipping_and_tax_estimates(self):
        cart = Cart.objects.create(session_key=self.client.session.session_key)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        context = get_cart_financial_context(cart, shipping_region='Nairobi')

        self.assertEqual(context['shipping_cost'], Decimal('250.00'))
        self.assertEqual(context['tax_amount'], Decimal('8.00'))
        self.assertEqual(context['estimated_total'], Decimal('308.00'))


class AddToCartViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shirts', slug='shirts')
        self.product = Product.objects.create(
            name='Classic Shirt',
            slug='classic-shirt',
            description='A test shirt',
            category=self.category,
            base_price=49.99,
            visibility=Product.Visibility.PUBLISHED,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='CS-001',
            size='M',
            color='Black',
            price_adjustment=0,
        )

    def test_add_to_cart_returns_json_for_ajax_request(self):
        response = self.client.post(
            reverse('orders:add_to_cart'),
            {'variant_id': str(self.variant.id), 'quantity': 2},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['status'], 'success')

    def test_add_to_cart_handles_invalid_json_body_without_crashing(self):
        response = self.client.post(
            reverse('orders:add_to_cart'),
            b'\x80invalid',
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['success'])

    def test_product_detail_template_contains_cart_form_fields(self):
        rendered = render_to_string('products/product_detail.html', {'product': self.product, 'colors': [], 'sizes': []})

        self.assertIn('name="product_id"', rendered)
        self.assertIn('name="variant_id"', rendered)
        self.assertIn('name="quantity"', rendered)

    def test_product_detail_template_uses_ajax_add_to_cart_form(self):
        rendered = render_to_string('products/product_detail.html', {'product': self.product, 'colors': [], 'sizes': []})

        self.assertIn('id="add-to-cart-form"', rendered)
        self.assertIn('submitAddToCartForm', rendered)

    def test_add_to_cart_falls_back_to_product_variant_when_variant_id_missing(self):
        response = self.client.post(
            reverse('orders:add_to_cart'),
            {'product_id': str(self.product.id), 'variant_id': '', 'quantity': 1},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('orders:cart'))

    def test_add_to_cart_handles_empty_quantity_from_form_post(self):
        response = self.client.post(
            reverse('orders:add_to_cart'),
            {'variant_id': str(self.variant.id), 'quantity': ''},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('orders:cart'))

    def test_add_to_cart_handles_invalid_product_id_without_crashing(self):
        response = self.client.post(
            reverse('orders:add_to_cart'),
            {'product_id': 'not-a-uuid', 'variant_id': '', 'quantity': 1},
        )

        self.assertEqual(response.status_code, 302)



class SaveForLaterTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shirts', slug='shirts')
        self.product = Product.objects.create(
            name='Classic Shirt',
            slug='classic-shirt',
            description='A test shirt',
            category=self.category,
            base_price=49.99,
            visibility=Product.Visibility.PUBLISHED,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='CS-002',
            size='M',
            color='Blue',
            price_adjustment=0,
            is_active=True,
        )

    def test_save_for_later_moves_item_into_session(self):
        # Add to cart first
        response = self.client.post(reverse('orders:add_to_cart'), {'variant_id': str(self.variant.id), 'quantity': 1})
        cart = Cart.objects.get(session_key=self.client.session.session_key)
        item = CartItem.objects.filter(cart=cart, variant=self.variant).first()
        # Save for later
        response = self.client.post(reverse('orders:save_for_later', args=[str(item.id)]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/'))
        session_saved = self.client.session.get('saved_for_later', [])
        self.assertIn(str(self.variant.id), session_saved)

    def test_move_saved_to_cart_restores_item(self):
        # simulate saved variant in session
        session = self.client.session
        session['saved_for_later'] = [str(self.variant.id)]
        session.save()

        response = self.client.post(reverse('orders:move_saved_to_cart', args=[str(self.variant.id)]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/'))
        cart = Cart.objects.get(session_key=self.client.session.session_key)
        self.assertTrue(CartItem.objects.filter(cart=cart, variant=self.variant).exists())
