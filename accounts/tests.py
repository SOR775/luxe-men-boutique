from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.context_processors import admin_permissions

from escrow.models import EscrowTransaction
from payments.models import Payment
from support.models import SupportMessage, SupportTicket
from .models import Administrator, Permission, Role
from .views import AdminDashboardView, DashboardView, SupportHistoryView, build_public_url


class DashboardViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(
            email='customer@example.com',
            username='customer',
            password='secret123',
        )

    def test_dashboard_wishlist_count_uses_wishlist_items_model(self):
        from products.models import Product, Category, Brand, WishlistItem

        category = Category.objects.create(name='Suits', slug='suits')
        brand = Brand.objects.create(name='Test Brand', slug='test-brand')
        product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            description='A test product',
            category=category,
            brand=brand,
            base_price=1000,
        )
        WishlistItem.objects.create(user=self.user, product=product)

        request = self.factory.get('/accounts/dashboard/')
        request.user = self.user

        view = DashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['wishlist_count'], 1)

    def test_dashboard_includes_address_summary_context(self):
        request = self.factory.get('/accounts/dashboard/')
        request.user = self.user

        view = DashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertIn('address_count', context)
        self.assertEqual(context['address_count'], 0)
        self.assertIn('default_address', context)
        self.assertIsNone(context['default_address'])

    def test_dashboard_context_includes_referral_and_loyalty_data(self):
        self.user.loyalty_points = 120
        self.user.referral_code = 'WELCOME10'
        self.user.save()

        request = self.factory.get('/accounts/dashboard/')
        request.user = self.user

        view = DashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['loyalty_points'], 120)
        self.assertEqual(context['referral_code'], 'WELCOME10')


class SupportHistoryViewTests(TestCase):
    def test_support_history_view_renders_tickets_with_messages(self):
        user = get_user_model().objects.create_user(email='support@example.com', username='supportuser', password='secret123')
        ticket = SupportTicket.objects.create(
            user=user,
            email=user.email,
            subject='Order issue',
            description='Need help with my order',
        )
        SupportMessage.objects.create(ticket=ticket, sender=user, body='Hello there', is_from_customer=True)

        request = RequestFactory().get('/accounts/support/')
        request.user = user

        view = SupportHistoryView()
        view.request = request
        context = view.get_context_data()

        self.assertIn('tickets', context)
        self.assertEqual(context['tickets'].count(), 1)


class PublicUrlGenerationTests(TestCase):
    def test_build_public_url_prefers_site_url_for_emails(self):
        request = RequestFactory().get('/accounts/register/')
        request.META['HTTP_HOST'] = 'localhost:8000'

        with override_settings(SITE_URL='https://example.ngrok-free.app'):
            url = build_public_url(request, '/accounts/verify-email/test-token/')

        self.assertEqual(url, 'https://example.ngrok-free.app/accounts/verify-email/test-token/')

    def test_build_public_url_uses_request_host_for_public_tunnels(self):
        request = RequestFactory().get('/accounts/register/', secure=True)
        request.META['HTTP_HOST'] = 'abc123.ngrok-free.app'

        with override_settings(SITE_URL='http://localhost:8000'):
            url = build_public_url(request, '/accounts/verify-email/test-token/')

        self.assertEqual(url, 'https://abc123.ngrok-free.app/accounts/verify-email/test-token/')


class ReturnRequestsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='u@example.com', username='u', password='pw')
        # create an order and a return request
        from orders.models import Order, ReturnRequest
        order = Order.objects.create(
            order_number='LM00001',
            subtotal=0,
            shipping_cost=0,
            discount_amount=0,
            total=0,
            shipping_name='Test',
            shipping_phone='000',
            shipping_email='u@example.com',
            shipping_address='here',
            shipping_city='Nairobi',
            user=self.user,
        )
        ReturnRequest.objects.create(order=order, user=self.user, type=ReturnRequest.Type.RETURN, reason='Need refund')

    def test_returns_page_shows_requests_for_user(self):
        from django.test import RequestFactory
        rf = RequestFactory()
        request = rf.get('/accounts/returns/')
        request.user = self.user
        from .views import ReturnRequestsView
        view = ReturnRequestsView()
        view.request = request
        ctx = view.get_context_data()
        self.assertIn('returns', ctx)
        self.assertEqual(len(ctx['returns']), 1)


class AdminDashboardAccessTests(TestCase):
    def test_anonymous_user_is_redirected_to_login_instead_of_crashing(self):
        request = RequestFactory().get(reverse('accounts:admin_dashboard'))
        request.user = AnonymousUser()

        response = AdminDashboardView.as_view()(request)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_staff_users_without_admin_profile_still_get_sidebar_permissions(self):
        staff_user = get_user_model().objects.create_user(
            email='staff-no-profile@example.com',
            username='staff-no-profile',
            password='secret123',
            is_staff=True,
        )

        request = RequestFactory().get(reverse('accounts:admin_dashboard'))
        request.user = staff_user

        context = admin_permissions(request)

        self.assertIn('access_admin_dashboard', context['user_admin_permissions'])
        self.assertIn('access_support_queue', context['user_admin_permissions'])
        self.assertIn('access_audit_log', context['user_admin_permissions'])
        self.assertIn('access_settings', context['user_admin_permissions'])
        self.assertNotIn('access_orders', context['user_admin_permissions'])
        self.assertNotIn('access_products', context['user_admin_permissions'])


class AdminDashboardMetricsTests(TestCase):
    def test_dashboard_exposes_order_status_breakdown_and_alert_counts(self):
        from orders.models import Order

        user = get_user_model().objects.create_user(
            email='ops@example.com',
            username='ops-admin',
            password='secret123',
        )

        pending_order = Order.objects.create(
            order_number='LM00001',
            user=user,
            subtotal=1000,
            shipping_cost=0,
            discount_amount=0,
            total=1000,
            shipping_name='Ops Admin',
            shipping_phone='0700000000',
            shipping_email='ops@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.UNPAID,
        )
        paid_order = Order.objects.create(
            order_number='LM00002',
            user=user,
            subtotal=2000,
            shipping_cost=0,
            discount_amount=0,
            total=2000,
            shipping_name='Ops Admin',
            shipping_phone='0700000000',
            shipping_email='ops@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            status=Order.Status.PAID,
            payment_status=Order.PaymentStatus.PAID,
        )

        Payment.objects.create(
            order=pending_order,
            method=Payment.Method.MPESA,
            status=Payment.Status.FAILED,
            amount=1000,
            currency='KES',
            reference='PAY-FAILED',
            description='Failed payment alert',
        )

        failed_payment = Payment.objects.create(
            order=paid_order,
            method=Payment.Method.CARD,
            status=Payment.Status.PROCESSING,
            amount=2000,
            currency='KES',
            reference='PAY-PENDING',
            description='Processing payment alert',
        )

        EscrowTransaction.objects.create(
            order=paid_order,
            payment=failed_payment,
            buyer=user,
            amount=2000,
            currency='KES',
            status=EscrowTransaction.Status.SHIPPED,
        )

        request = RequestFactory().get('/accounts/admin/dashboard/')
        view = AdminDashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['orders_by_status']['pending'], 1)
        self.assertEqual(context['orders_by_status']['paid'], 1)
        self.assertEqual(context['payment_alert_count'], 2)
        self.assertEqual(context['escrow_alert_count'], 1)
        self.assertEqual(len(context['payment_alerts']), 2)
        self.assertEqual(len(context['escrow_alerts']), 1)
        self.assertIn('attention_queue', context)
        self.assertGreaterEqual(len(context['attention_queue']), 2)
        self.assertTrue(all('action_url' in item for item in context['attention_queue']))
        self.assertTrue(all('age_display' in item for item in context['attention_queue']))
        self.assertTrue(any(item['kind'] == 'escrow' and item.get('release_url') for item in context['attention_queue']))
        self.assertEqual(context['attention_queue'][0]['kind'], 'payment')

    def test_dashboard_attention_queue_can_be_filtered_by_alert_type(self):
        from orders.models import Order

        user = get_user_model().objects.create_user(
            email='ops-filter@example.com',
            username='ops-filter',
            password='secret123',
        )

        order = Order.objects.create(
            order_number='LM00003',
            user=user,
            subtotal=1500,
            shipping_cost=0,
            discount_amount=0,
            total=1500,
            shipping_name='Ops Admin',
            shipping_phone='0700000000',
            shipping_email='ops-filter@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.UNPAID,
        )

        payment = Payment.objects.create(
            order=order,
            method=Payment.Method.MPESA,
            status=Payment.Status.FAILED,
            amount=1500,
            currency='KES',
            reference='PAY-FILTER',
            description='Filtered payment alert',
        )

        EscrowTransaction.objects.create(
            order=order,
            payment=payment,
            buyer=user,
            amount=1500,
            currency='KES',
            status=EscrowTransaction.Status.SHIPPED,
        )

        request = RequestFactory().get('/accounts/admin/dashboard/?alert_type=payment')
        view = AdminDashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['attention_filter'], 'payment')
        self.assertEqual(context['payment_alert_count'], 1)
        self.assertTrue(all(item['kind'] == 'payment' for item in context['attention_queue']))

    def test_dashboard_attention_queue_exposes_open_and_resolved_states(self):
        from orders.models import Order

        user = get_user_model().objects.create_user(
            email='ops-review@example.com',
            username='ops-review',
            password='secret123',
        )

        order = Order.objects.create(
            order_number='LM00004',
            user=user,
            subtotal=1800,
            shipping_cost=0,
            discount_amount=0,
            total=1800,
            shipping_name='Ops Admin',
            shipping_phone='0700000000',
            shipping_email='ops-review@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
        )

        payment = Payment.objects.create(
            order=order,
            method=Payment.Method.CARD,
            status=Payment.Status.COMPLETED,
            amount=1800,
            currency='KES',
            reference='PAY-RESOLVED',
            description='Resolved payment alert',
        )

        escrow = EscrowTransaction.objects.get(payment=payment)
        escrow.status = EscrowTransaction.Status.RELEASED
        escrow.save(update_fields=['status'])

        request = RequestFactory().get('/accounts/admin/dashboard/?alert_state=resolved')
        view = AdminDashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['attention_state'], 'resolved')
        self.assertTrue(all(item['state'] == 'resolved' for item in context['attention_queue']))

    def test_dashboard_attention_queue_uses_session_reviewed_state(self):
        from orders.models import Order

        user = get_user_model().objects.create_user(
            email='ops-reviewed@example.com',
            username='ops-reviewed',
            password='secret123',
        )

        order = Order.objects.create(
            order_number='LM00005',
            user=user,
            subtotal=2200,
            shipping_cost=0,
            discount_amount=0,
            total=2200,
            shipping_name='Ops Admin',
            shipping_phone='0700000000',
            shipping_email='ops-reviewed@example.com',
            shipping_address='Nairobi',
            shipping_city='Nairobi',
            shipping_country='Kenya',
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.UNPAID,
        )

        payment = Payment.objects.create(
            order=order,
            method=Payment.Method.MPESA,
            status=Payment.Status.PENDING,
            amount=2200,
            currency='KES',
            reference='PAY-REVIEWED',
            description='Open payment alert',
        )

        EscrowTransaction.objects.create(
            order=order,
            payment=payment,
            buyer=user,
            amount=2200,
            currency='KES',
            status=EscrowTransaction.Status.FUNDED,
        )

        request = RequestFactory().get('/accounts/admin/dashboard/')
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session['reviewed_dashboard_alerts'] = [f'payment:{payment.id}']
        request.session.save()

        view = AdminDashboardView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['reviewed_alert_count'], 1)
        self.assertTrue(all(item['kind'] == 'escrow' for item in context['attention_queue']))


class AdminSidebarTemplateTests(TestCase):
    def test_admin_sidebar_defaults_to_open_state(self):
        request = RequestFactory().get('/accounts/admin/dashboard/')
        request.user = get_user_model().objects.create_user(
            email='demo-admin@example.com',
            username='demo-admin',
            password='secret123',
            is_staff=True,
        )

        html = render_to_string(
            'accounts/admin_sidebar.html',
            {
                'active': 'dashboard',
                'user_admin_permissions': [
                    'access_admin_dashboard',
                    'access_inventory_dashboard',
                    'access_inventory_sku',
                    'access_inventory_stock_history',
                ],
            },
            request=request,
        )

        self.assertIn('x-data="{ open: true }"', html)


class DefaultRoleSeedTests(TestCase):
    def test_seed_default_roles_creates_role_permissions(self):
        call_command('seed_default_roles')

        role_names = {
            'Super Owner',
            'Store Manager',
            'Inventory Manager',
            'Support Agent',
            'Finance Admin',
        }
        self.assertTrue(set(Role.objects.filter(name__in=role_names).values_list('name', flat=True)) == role_names)

        permissions = Permission.objects.filter(codename__in=[
            'access_admin_dashboard',
            'access_orders',
            'access_inventory_dashboard',
            'access_support_queue',
            'access_finance',
            'manage_staff_roles',
        ])
        self.assertGreaterEqual(permissions.count(), 6)

        super_owner = Role.objects.get(name='Super Owner')
        self.assertTrue(super_owner.permissions.filter(codename='manage_staff_roles').exists())


class AdminPermissionChecksTests(TestCase):
    def test_administrator_role_permissions_are_checked_from_role_membership(self):
        call_command('seed_default_roles')
        user = get_user_model().objects.create_user(
            email='admin@example.com',
            username='admin-user',
            password='secret123',
            is_staff=True,
        )
        admin_profile = Administrator.objects.create(user=user, department='Operations')
        inventory_role = Role.objects.get(name='Inventory Manager')
        admin_profile.roles.add(inventory_role)

        self.assertTrue(admin_profile.has_permission('access_inventory_dashboard'))
        self.assertFalse(admin_profile.has_permission('access_support_queue'))
