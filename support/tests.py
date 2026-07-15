from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from notifications.models import Notification
from orders.models import Order
from .models import SupportMessage, SupportTicket


class SupportChatTests(TestCase):
    def test_admin_dashboard_lists_support_tickets_for_staff(self):
        staff = get_user_model().objects.create_user(
            username='support-admin',
            email='support-admin@example.com',
            password='secret123',
            is_staff=True,
        )
        customer = get_user_model().objects.create_user(
            username='support-customer',
            email='support-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='support-customer@example.com',
            subject='Order issue',
            description='Need help with my order',
        )
        SupportMessage.objects.create(ticket=ticket, sender=customer, body='I need help urgently', is_from_customer=True)

        self.client.force_login(staff)
        response = self.client.get(reverse('accounts:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Order issue')
        self.assertContains(response, 'I need help urgently')
    def test_user_can_start_support_chat_and_view_thread(self):
        user = get_user_model().objects.create_user(
            username='chat-user',
            email='chat@example.com',
            password='secret123',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('support:create_ticket'),
            {'subject': 'Sizing help', 'message': 'Do you have this in a larger size?'}
        )

        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get(email='chat@example.com')
        self.assertEqual(ticket.subject, 'Sizing help')
        self.assertTrue(SupportMessage.objects.filter(ticket=ticket, is_from_customer=True).exists())

        thread_response = self.client.get(reverse('support:ticket_thread', kwargs={'pk': ticket.pk}))
        self.assertEqual(thread_response.status_code, 200)
        self.assertContains(thread_response, 'Do you have this in a larger size?')

    def test_new_ticket_notifies_staff_users(self):
        staff = get_user_model().objects.create_user(
            username='notify-staff',
            email='notify-staff@example.com',
            password='secret123',
            is_staff=True,
        )
        user = get_user_model().objects.create_user(
            username='notify-customer',
            email='notify-customer@example.com',
            password='secret123',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('support:create_ticket'),
            {'subject': 'Shipment issue', 'message': 'My parcel has not arrived'}
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(user=staff, title='New support ticket').exists())

    def test_customer_reply_notifies_staff_users(self):
        staff = get_user_model().objects.create_user(
            username='reply-notify-staff',
            email='reply-notify-staff@example.com',
            password='secret123',
            is_staff=True,
        )
        customer = get_user_model().objects.create_user(
            username='reply-notify-customer',
            email='reply-notify-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='reply-notify-customer@example.com',
            subject='Follow-up issue',
            description='Need more help',
        )

        self.client.force_login(customer)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'I still need help with this issue'}
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(
                user=staff,
                title='New customer reply',
            ).exists()
        )

    def test_support_ticket_gets_automatic_acknowledgement_when_staff_are_available(self):
        staff = get_user_model().objects.create_user(
            username='ack-staff',
            email='ack-staff@example.com',
            password='secret123',
            is_staff=True,
        )
        user = get_user_model().objects.create_user(
            username='ack-user',
            email='ack-user@example.com',
            password='secret123',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('support:create_ticket'),
            {'subject': 'Need help', 'message': 'I have a question'}
        )

        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get(email='ack-user@example.com')
        self.assertTrue(
            SupportMessage.objects.filter(
                ticket=ticket,
                body__icontains='Thanks for contacting Luxe Men',
            ).exists()
        )
        self.assertTrue(Notification.objects.filter(user=staff, title='New support ticket').exists())

    def test_support_ticket_auto_replies_when_no_staff_are_available(self):
        user = get_user_model().objects.create_user(
            username='auto-reply-user',
            email='auto-reply@example.com',
            password='secret123',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('support:create_ticket'),
            {'subject': 'Queue me', 'message': 'I need help with this order'}
        )

        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get(email='auto-reply@example.com')
        self.assertTrue(
            SupportMessage.objects.filter(
                ticket=ticket,
                body__icontains='No support agent is currently available',
            ).exists()
        )

    def test_human_support_requests_trigger_an_urgent_staff_alert(self):
        staff = get_user_model().objects.create_user(
            username='human-support-staff',
            email='human-support-staff@example.com',
            password='secret123',
            is_staff=True,
        )
        user = get_user_model().objects.create_user(
            username='human-support-user',
            email='human-support-user@example.com',
            password='secret123',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('support:create_ticket'),
            {'subject': 'Live help', 'message': 'I need human support right now'}
        )

        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get(email='human-support-user@example.com')
        self.assertTrue(
            SupportMessage.objects.filter(ticket=ticket, body__icontains='human support').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=staff, title='Urgent human support request').exists()
        )

    def test_staff_can_view_ticket_thread(self):
        user = get_user_model().objects.create_user(
            username='staff-user',
            email='staff@example.com',
            password='secret123',
            is_staff=True,
        )
        customer = get_user_model().objects.create_user(
            username='customer-user',
            email='customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='customer@example.com',
            subject='Order issue',
            description='Need help with my order',
        )
        SupportMessage.objects.create(ticket=ticket, sender=customer, body='Hello there', is_from_customer=True)

        self.client.force_login(user)
        response = self.client.get(reverse('support:ticket_thread', kwargs={'pk': ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello there')

    def test_chat_messages_can_be_sent_without_full_page_reload(self):
        customer = get_user_model().objects.create_user(
            username='ajax-customer',
            email='ajax-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='ajax-customer@example.com',
            subject='Quick reply',
            description='Need a fast response',
        )

        self.client.force_login(customer)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'I need help quickly'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertTrue(SupportMessage.objects.filter(ticket=ticket, body='I need help quickly').exists())

    def test_ajax_reply_includes_bot_message_for_customer_queries(self):
        customer = get_user_model().objects.create_user(
            username='ajax-bot-customer',
            email='ajax-bot-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='ajax-bot-customer@example.com',
            subject='Order question',
            description='Need help with my order',
        )

        self.client.force_login(customer)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'Where is my order?'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertIn('order tracking', response.json()['reply_body'].lower())

    def test_bot_acknowledges_when_customer_shares_order_details(self):
        customer = get_user_model().objects.create_user(
            username='details-bot-customer',
            email='details-bot-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='details-bot-customer@example.com',
            subject='Order details',
            description='Need help with my order',
        )

        self.client.force_login(customer)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'My order number is 12345 and my email is test@example.com'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertIn('shared', response.json()['reply_body'].lower())

    def test_bot_can_report_order_status_from_account_details(self):
        customer = get_user_model().objects.create_user(
            username='order-status-customer',
            email='order-status-customer@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='order-status-customer@example.com',
            subject='Order status',
            description='Need help with my order',
        )
        Order.objects.create(
            order_number='LM12345678',
            user=customer,
            shipping_name='Test Customer',
            shipping_phone='0712345678',
            shipping_email=customer.email,
            shipping_address='1 Test Street',
            shipping_city='Nairobi',
            subtotal='100.00',
            total='100.00',
            status=Order.Status.SHIPPED,
            payment_status=Order.PaymentStatus.PAID,
        )

        self.client.force_login(customer)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'Please check order LM12345678'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertIn('LM12345678', response.json()['reply_body'])
        self.assertIn('Shipped', response.json()['reply_body'])

    def test_staff_can_reply_from_thread_view(self):
        staff = get_user_model().objects.create_user(
            username='staff-reply-user',
            email='staff-reply@example.com',
            password='secret123',
            is_staff=True,
        )
        customer = get_user_model().objects.create_user(
            username='customer-reply-user',
            email='customer-reply@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='customer@example.com',
            subject='Delivery delay',
            description='My order is late',
        )

        self.client.force_login(staff)
        response = self.client.post(
            reverse('support:ticket_thread', kwargs={'pk': ticket.pk}),
            {'message': 'We are checking the shipment'}
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SupportMessage.objects.filter(ticket=ticket, body='We are checking the shipment').exists())

    def test_staff_can_close_ticket_from_thread_view(self):
        staff = get_user_model().objects.create_user(
            username='staff-close-user',
            email='staff-close@example.com',
            password='secret123',
            is_staff=True,
        )
        customer = get_user_model().objects.create_user(
            username='customer-close-user',
            email='customer-close@example.com',
            password='secret123',
        )
        ticket = SupportTicket.objects.create(
            user=customer,
            email='customer-close@example.com',
            subject='Resolved issue',
            description='Need to close this',
        )

        self.client.force_login(staff)
        response = self.client.post(reverse('support:close_ticket', kwargs={'pk': ticket.pk}))

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.CLOSED)
