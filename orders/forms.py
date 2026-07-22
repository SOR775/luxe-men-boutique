from django import forms

from .models import Coupon


class CouponForm(forms.ModelForm):
    valid_from = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    valid_until = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))

    class Meta:
        model = Coupon
        fields = [
            'code',
            'discount_type',
            'discount_value',
            'minimum_order_amount',
            'max_uses',
            'valid_from',
            'valid_until',
            'is_active',
        ]
