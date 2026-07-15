"""
core/admin_models.py — Admin Dashboard Models for System Settings & Content Moderation
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class SystemSettings(models.Model):
    """Centralized configuration for taxes, fees, shipping rates."""
    
    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'
    
    # Tax settings
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=16.0,
        help_text='Default tax rate as percentage (e.g., 16.0 = 16%)'
    )
    
    # Fee settings
    platform_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0,
        help_text='Platform commission percentage on each sale'
    )
    payment_processing_fee = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.5,
        help_text='Payment processing fee percentage'
    )
    
    # Shipping settings
    free_shipping_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=10000.0,
        help_text='Orders above this amount get free shipping'
    )
    base_shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=500.0,
        help_text='Base shipping cost in KES'
    )
    
    # Escrow settings
    auto_release_days = models.PositiveIntegerField(
        default=7,
        help_text='Auto-release escrow after N days if no dispute'
    )
    dispute_resolution_days = models.PositiveIntegerField(
        default=3,
        help_text='Time to resolve disputes in days'
    )
    
    # General settings
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True)
    allow_new_sellers = models.BooleanField(default=True)
    require_seller_verification = models.BooleanField(default=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='settings_updates'
    )
    
    def __str__(self):
        return 'System Settings'
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SystemSettings.objects.exists():
            self.pk = SystemSettings.objects.first().pk
        super().save(*args, **kwargs)


class ContentModerationQueue(models.Model):
    """Queue for approving product descriptions, reviews, images."""
    
    class ContentType(models.TextChoices):
        PRODUCT_DESCRIPTION = 'product_desc', _('Product Description')
        PRODUCT_IMAGE = 'product_image', _('Product Image')
        PRODUCT_REVIEW = 'product_review', _('Product Review')
        SELLER_PROFILE = 'seller_profile', _('Seller Profile')
    
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending Review')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Content reference
    content_type = models.CharField(max_length=20, choices=ContentType.choices)
    content_id = models.CharField(max_length=100, help_text='UUID/ID of the content being moderated')
    
    # Content details
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Submitted by
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='moderation_submissions'
    )
    
    # Status & review
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='moderation_reviews'
    )
    rejection_reason = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    
    # Flagged content
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['content_type', 'status']),
        ]
    
    def __str__(self):
        return f'{self.get_content_type_display()} — {self.title} ({self.get_status_display()})'


class UserSuspension(models.Model):
    """Track user bans and suspensions."""
    
    class SuspensionType(models.TextChoices):
        SUSPENDED = 'suspended', _('Suspended')
        BANNED = 'banned', _('Banned')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='suspension'
    )
    
    suspension_type = models.CharField(
        max_length=20, choices=SuspensionType.choices
    )
    reason = models.TextField()
    suspended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='suspensions_issued'
    )
    
    # Suspension period
    suspended_at = models.DateTimeField(auto_now_add=True)
    suspended_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Appeals
    appeal_submitted = models.BooleanField(default=False)
    appeal_text = models.TextField(blank=True)
    appeal_date = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True, help_text='Internal admin notes')
    
    class Meta:
        ordering = ['-suspended_at']
    
    def __str__(self):
        return f'{self.user.username} — {self.get_suspension_type_display()}'
    
    def is_active_suspension(self):
        """Check if suspension is currently active."""
        if not self.is_active:
            return False
        if self.suspended_until and self.suspended_until < timezone.now():
            return False
        return True


from django.utils import timezone
