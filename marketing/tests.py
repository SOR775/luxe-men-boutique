from django.test import TestCase
from django.urls import reverse

from .models import BlogPost, NewsletterSubscriber


class MarketingTests(TestCase):
    def test_marketing_home_page_shows_latest_posts_and_newsletter_cta(self):
        BlogPost.objects.create(
            title='Spring Edit',
            slug='spring-edit',
            excerpt='A fresh look for the season.',
            content='This is the blog post body.',
            is_published=True,
        )

        response = self.client.get(reverse('marketing:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spring Edit')
        self.assertContains(response, 'Subscribe')

    def test_blog_posts_are_listed_on_blog_page(self):
        BlogPost.objects.create(
            title='Spring Edit',
            slug='spring-edit',
            excerpt='A fresh look for the season.',
            content='This is the blog post body.',
            is_published=True,
        )

        response = self.client.get(reverse('marketing:blog_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spring Edit')
        self.assertContains(response, 'A fresh look for the season.')

    def test_blog_post_detail_page_renders_full_content(self):
        BlogPost.objects.create(
            title='Summer Layers',
            slug='summer-layers',
            excerpt='A lighter approach to dressing.',
            content='Layer with linen and relaxed tailoring.',
            is_published=True,
        )

        response = self.client.get(reverse('marketing:blog_detail', kwargs={'slug': 'summer-layers'}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Summer Layers')
        self.assertContains(response, 'Layer with linen and relaxed tailoring.')

    def test_newsletter_subscription_creates_subscriber(self):
        response = self.client.post(
            reverse('marketing:newsletter_subscribe'),
            {'email': 'reader@example.com'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(NewsletterSubscriber.objects.filter(email='reader@example.com').exists())
