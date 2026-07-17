from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AnalyticsDashboardTests(TestCase):
    def test_staff_user_can_open_analytics_dashboard(self):
        staff = get_user_model().objects.create_user(
            username='analytics-admin',
            email='analytics-admin@example.com',
            password='secret123',
            is_staff=True,
        )

        self.client.force_login(staff)
        response = self.client.get(reverse('analytics:dashboard'))

        self.assertEqual(response.status_code, 200)
