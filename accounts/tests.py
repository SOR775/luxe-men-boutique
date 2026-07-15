from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

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
