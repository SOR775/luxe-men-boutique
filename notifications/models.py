import uuid
import logging
import threading

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

logger = logging.getLogger(__name__)


class Notification(models.Model):
    """In-app and email notifications for authenticated users."""

    class Level(models.TextChoices):
        INFO = 'info', _('Info')
        SUCCESS = 'success', _('Success')
        WARNING = 'warning', _('Warning')
        ERROR = 'error', _('Error')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    target_url = models.CharField(max_length=255, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    is_read = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')

    def __str__(self):
        return f'{self.title} — {self.user.email}'

    @property
    def payload(self):
        return {
            'id': str(self.id),
            'title': self.title,
            'message': self.message,
            'target_url': self.target_url,
            'level': self.level,
            'created_at': self.created_at.isoformat(),
        }

    def send_email(self):
        thread = threading.Thread(
            target=self._send_email_in_background,
            name=f'notification-email-{self.pk}',
            daemon=True,
        )
        thread.start()

    def _send_email_in_background(self):
        if not self.user.email or not getattr(self.user, 'email_notifications', True):
            return

        try:
            subject = f'[{getattr(settings, "SITE_NAME", "LUXE MEN")}] {self.title}'
            send_mail(
                subject=subject,
                message=self.message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@luxemen.com'),
                recipient_list=[self.user.email],
                fail_silently=True,
            )
        except Exception:
            logger.exception('Failed to send notification email for %s', self.user)

    def send_sms(self):
        thread = threading.Thread(
            target=self._send_sms_in_background,
            name=f'notification-sms-{self.pk}',
            daemon=True,
        )
        thread.start()

    def _send_sms_in_background(self):
        if not getattr(self.user, 'sms_notifications', True) or not getattr(self.user, 'phone', None):
            return

        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        from_number = getattr(settings, 'TWILIO_FROM_NUMBER', None)

        if not all([account_sid, auth_token, from_number]):
            return

        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=self.message,
                from_=from_number,
                to=self.user.phone,
            )
        except ImportError:
            logger.warning('Twilio library not installed; SMS notifications disabled.')
        except Exception:
            logger.exception('Failed to send SMS notification to %s', self.user)

    def broadcast(self):
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'notifications_{self.user.pk}',
                {
                    'type': 'notification.message',
                    'payload': self.payload,
                }
            )
        except Exception:
            pass

    @classmethod
    def create(cls, user, title, message, target_url='', level='info', send_sms=False):
        notification = cls.objects.create(
            user=user,
            title=title,
            message=message,
            target_url=target_url,
            level=level,
        )
        notification.broadcast()
        notification.send_email()
        if send_sms:
            notification.send_sms()
        return notification

    @classmethod
    def broadcast_to_subscribers(cls, title, message, target_url='', level='info'):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(
            is_active=True,
            newsletter_subscribed=True,
            email_notifications=True,
        )
        for user in users.iterator():
            cls.create(
                user=user,
                title=title,
                message=message,
                target_url=target_url,
                level=level,
            )

