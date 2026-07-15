"""
accounts/models.py — User, RBAC, Auth Models

Architecture:
  - User: Custom user model (extends AbstractBaseUser)
  - SuperAdministrator: Singleton, unrestricted control
  - Role: Named permission bundles (e.g., Store Manager)
  - Permission: Granular action permissions
  - Administrator: Staff linked to roles
  - LoginHistory: Audit trail for authentication
  - UserAddress: Multiple shipping addresses
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings


# ─── User Manager ─────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    """Custom manager supporting email-based authentication."""

    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Email address is required.'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_email_verified', True)
        return self.create_user(email, username, password, **extra_fields)


# ─── User Model ───────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for LUXE MEN.
    Uses email as the primary authentication identifier.
    """

    class AccountType(models.TextChoices):
        CUSTOMER = 'customer', _('Customer')
        ADMINISTRATOR = 'administrator', _('Administrator')
        SUPER_ADMIN = 'super_admin', _('Super Administrator')

    class Gender(models.TextChoices):
        MALE = 'male', _('Male')
        FEMALE = 'female', _('Female')
        OTHER = 'other', _('Other')
        PREFER_NOT = 'prefer_not', _('Prefer not to say')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core fields
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    # Profile
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=15, choices=Gender.choices, blank=True)
    bio = models.TextField(blank=True)

    # Account type & status
    account_type = models.CharField(
        max_length=20, choices=AccountType.choices, default=AccountType.CUSTOMER
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)

    # Preferences
    dark_mode = models.BooleanField(default=False)
    newsletter_subscribed = models.BooleanField(default=False)
    sms_notifications = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)

    # Security
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Loyalty
    loyalty_points = models.PositiveIntegerField(default=0)
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='referrals'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'accounts_user'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}>'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    @property
    def is_locked(self):
        """Check if the account is currently locked due to failed logins."""
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    @property
    def is_super_admin(self):
        return self.account_type == self.AccountType.SUPER_ADMIN

    @property
    def is_admin(self):
        return self.account_type in [
            self.AccountType.ADMINISTRATOR,
            self.AccountType.SUPER_ADMIN
        ]

    def save(self, *args, **kwargs):
        # Auto-generate referral code on first save
        if not self.referral_code:
            import secrets
            self.referral_code = secrets.token_urlsafe(8).upper()[:10]
        super().save(*args, **kwargs)

    def has_admin_permission(self, codename: str) -> bool:
        """Return whether this user can perform a role-scoped admin action."""
        if self.is_super_admin or self.is_superuser:
            return True

        try:
            admin_profile = self.admin_profile
        except Administrator.DoesNotExist:
            return False

        return admin_profile.has_permission(codename)


# ─── Email Verification Token ─────────────────────────────────────────────────

class EmailVerificationToken(models.Model):
    """Token for email address verification."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification_token')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f'Verification token for {self.user.email}'


# ─── Password Reset Token ─────────────────────────────────────────────────────

class PasswordResetToken(models.Model):
    """Token for password reset flow."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_resets')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class EmailLoginCode(models.Model):
    """One-time code for passwordless email login."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_codes')
    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Email Login Code')
        verbose_name_plural = _('Email Login Codes')

    def __str__(self):
        return f'Login code for {self.email} — {self.code}'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def mark_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_at'])


# ─── RBAC: Permission ─────────────────────────────────────────────────────────

class Permission(models.Model):
    """
    Granular permission unit.
    Examples: 'products.can_add', 'orders.can_approve', 'reports.can_export'
    """
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    module = models.CharField(max_length=50)  # e.g., 'products', 'orders'
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['module', 'codename']

    def __str__(self):
        return f'{self.module}.{self.codename}'


# ─── RBAC: Role ───────────────────────────────────────────────────────────────

class Role(models.Model):
    """
    Named permission bundle. Only Super Administrator can create/delete roles.
    """

    class RoleType(models.TextChoices):
        STORE_MANAGER = 'store_manager', _('Store Manager')
        INVENTORY_MANAGER = 'inventory_manager', _('Inventory Manager')
        SALES_MANAGER = 'sales_manager', _('Sales Manager')
        MARKETING_MANAGER = 'marketing_manager', _('Marketing Manager')
        FINANCE_MANAGER = 'finance_manager', _('Finance Manager')
        CUSTOMER_SUPPORT = 'customer_support', _('Customer Support')
        DELIVERY_MANAGER = 'delivery_manager', _('Delivery Manager')
        CONTENT_MANAGER = 'content_manager', _('Content Manager')
        PRODUCT_MANAGER = 'product_manager', _('Product Manager')
        REPORT_VIEWER = 'report_viewer', _('Report Viewer')
        CUSTOM = 'custom', _('Custom Role')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    role_type = models.CharField(max_length=30, choices=RoleType.choices, default=RoleType.CUSTOM)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='roles_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ─── RBAC: Administrator ──────────────────────────────────────────────────────

class Administrator(models.Model):
    """
    Extends User with admin-specific data.
    Can only be created/deleted by Super Administrator.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    roles = models.ManyToManyField(Role, blank=True, related_name='administrators')
    extra_permissions = models.ManyToManyField(
        Permission, blank=True, related_name='extra_administrators'
    )
    is_active = models.BooleanField(default=True)
    department = models.CharField(max_length=100, blank=True)
    employee_id = models.CharField(max_length=50, blank=True, unique=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='admins_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Admin: {self.user.get_full_name()}'

    def has_permission(self, codename: str) -> bool:
        """
        Check if this administrator has a specific permission.
        Super Admin always returns True.
        """
        if self.user.is_super_admin:
            return True
        role_perms = Permission.objects.filter(
            roles__in=self.roles.all(), codename=codename
        ).exists()
        if role_perms:
            return True
        return self.extra_permissions.filter(codename=codename).exists()


# ─── Super Administrator (Singleton) ──────────────────────────────────────────

class SuperAdministrator(models.Model):
    """
    Singleton model — only ONE Super Administrator may exist.
    Enforced at model save level.
    """
    user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name='super_admin_profile'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Super Administrator'
        verbose_name_plural = 'Super Administrator'

    def save(self, *args, **kwargs):
        if not self.pk and SuperAdministrator.objects.exists():
            raise ValueError('Only one Super Administrator is allowed.')
        self.user.account_type = User.AccountType.SUPER_ADMIN
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Super Admin: {self.user.get_full_name()}'


# ─── User Address Book ────────────────────────────────────────────────────────

class UserAddress(models.Model):
    """Multiple shipping/billing addresses per user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home')  # e.g., Home, Work, Other
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state_county = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Kenya')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.label} — {self.full_name}, {self.city}'

    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            UserAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


# ─── Login History ────────────────────────────────────────────────────────────

class LoginHistory(models.Model):
    """Audit trail for all authentication events."""

    class LoginStatus(models.TextChoices):
        SUCCESS = 'success', _('Success')
        FAILED = 'failed', _('Failed')
        LOCKED = 'locked', _('Account Locked')
        LOGOUT = 'logout', _('Logout')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='login_history', null=True, blank=True
    )
    email_attempted = models.EmailField(blank=True)  # Track failed attempts by email
    status = models.CharField(max_length=10, choices=LoginStatus.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Login Histories'


# ─── General Audit Log ───────────────────────────────────────────────────────


class AuditLog(models.Model):
    """Record administrative and important system actions for auditing."""

    ACTION_CHOICES = [
        ('user_update', 'User Update'),
        ('password_reset', 'Password Reset'),
        ('role_change', 'Role Change'),
        ('permission_change', 'Permission Change'),
        ('system', 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_performed')
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_received')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    message = models.TextField(blank=True)
    metadata = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        actor = self.actor.get_full_name() if self.actor else 'System'
        target = self.target_user.email if self.target_user else '—'
        return f'{self.get_action_display()} by {actor} on {target} at {self.created_at.isoformat()}'


# ─── Activity Log ─────────────────────────────────────────────────────────────

class ActivityLog(models.Model):
    """General user activity audit log."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activities')
    action = models.CharField(max_length=200)
    module = models.CharField(max_length=50)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.action}'
