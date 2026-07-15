from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Notification


class NotificationTests(TestCase):
    def test_marking_notification_read_redirects_to_target_url(self):
        user = get_user_model().objects.create_user(
            username='notif-user',
            email='notif@example.com',
            password='secret123',
        )
        notification = Notification.objects.create(
            user=user,
            title='Support update',
            message='A new message arrived',
            target_url='/tickets/42/',
        )

        self.client.force_login(user)
        response = self.client.post(reverse('notifications:mark_read', kwargs={'pk': notification.pk}))

        self.assertRedirects(response, '/tickets/42/', fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
