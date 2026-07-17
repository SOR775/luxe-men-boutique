from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_healthz_endpoint_returns_ok(self):
        response = self.client.get(reverse('core:healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
