"""
accounts/forms.py — Authentication & Profile Forms
"""
import re
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import UserAddress, Administrator, Role

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    """User registration form with validation."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password',
            'id': 'id_password',
        }),
        min_length=8,
        label=_('Password'),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'id': 'id_password_confirm',
        }),
        label=_('Confirm Password'),
    )
    agree_terms = forms.BooleanField(
        required=True,
        label=_('I agree to the Terms & Conditions'),
        error_messages={'required': _('You must accept the terms and conditions.')},
    )
    referral_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Referral Code (Optional)'}),
        label=_('Referral Code'),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Your email address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+254 7XX XXX XXX'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_('An account with this email already exists.'))
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise forms.ValidationError(_('Username can only contain letters, numbers, and underscores.'))
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(_('This username is already taken.'))
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError({'password_confirm': _('Passwords do not match.')})
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.is_email_verified = False
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Enhanced login form with remember-me support."""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email or Username',
            'autofocus': True,
        }),
        label=_('Email or Username'),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your password',
        }),
        label=_('Password'),
    )
    remember_me = forms.BooleanField(required=False, label=_('Remember Me'))

    error_messages = {
        'invalid_login': _(
            'Invalid email/username or password. '
            'Note: %(N)d failed attempts will lock your account.'
        ) % {'N': 5},
        'inactive': _('This account has been deactivated.'),
    }


class EmailLoginRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autofocus': True,
        }),
        label=_('Email Address'),
    )

    def clean_email(self):
        return self.cleaned_data.get('email', '').lower().strip()


class EmailLoginCodeForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autofocus': True,
        }),
        label=_('Email Address'),
    )
    code = forms.CharField(
        max_length=8,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter the 6-digit login code',
        }),
        label=_('Login Code'),
    )

    def clean_email(self):
        return self.cleaned_data.get('email', '').lower().strip()

    def clean_code(self):
        return self.cleaned_data.get('code', '').strip()


class ProfileUpdateForm(forms.ModelForm):
    """Profile editing form."""
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'username', 'phone',
            'date_of_birth', 'gender', 'bio', 'avatar',
            'newsletter_subscribed', 'sms_notifications', 'email_notifications',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'avatar': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class AddressForm(forms.ModelForm):
    """User address book form."""
    class Meta:
        model = UserAddress
        fields = [
            'label', 'full_name', 'phone',
            'address_line1', 'address_line2',
            'city', 'state_county', 'postal_code', 'country', 'is_default',
        ]
        widgets = {
            'label': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line1': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state_county': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
        }


class PasswordChangeForm(forms.Form):
    """Change password form requiring current password."""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_('Current Password'),
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_('New Password'),
        min_length=8,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_('Confirm New Password'),
    )

    def clean(self):
        cleaned_data = super().clean()
        new = cleaned_data.get('new_password')
        confirm = cleaned_data.get('confirm_password')
        if new and confirm and new != confirm:
            raise forms.ValidationError({'confirm_password': _('Passwords do not match.')})
        return cleaned_data


class ForgotPasswordForm(forms.Form):
    """Email form to initiate password reset."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your registered email',
        }),
        label=_('Email Address'),
    )


class ResetPasswordForm(forms.Form):
    """New password form for reset flow."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_('New Password'),
        min_length=8,
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_('Confirm Password'),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({'password_confirm': _('Passwords do not match.')})
        return cleaned_data


class StaffRoleAssignmentForm(forms.ModelForm):
    """Simple role assignment form for staff user records."""

    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.filter(is_active=True),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '6'}),
    )

    class Meta:
        model = Administrator
        fields = ['roles']


class AdminUserForm(forms.ModelForm):
    """Form for staff to edit user details (no password edits here)."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone', 'is_active', 'is_staff', 'is_email_verified']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        qs = User.objects.filter(email=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Another account with this email already exists.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        qs = User.objects.filter(username=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This username is already taken.')
        return username
