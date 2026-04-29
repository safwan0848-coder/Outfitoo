from django import forms
from django.utils import timezone
from .models import Coupon


class CouponForm(forms.ModelForm):
    """
    Admin form for creating / editing Coupons.
    Performs all business-rule validation server-side.
    """

    class Meta:
        model = Coupon
        fields = [
            'code', 'discount_type', 'discount_value',
            'min_amount', 'max_discount',
            'usage_limit', 'usage_limit_per_user',
            'start_date', 'expiry_date', 'is_active',
        ]
        widgets = {
            'start_date':  forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    # ── Field-level ──────────────────────────────────────────────

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        if not code:
            raise forms.ValidationError("Coupon code is required.")

        # Case-insensitive uniqueness (exclude self on edit)
        qs = Coupon.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A coupon with this code already exists.")
        return code

    def clean_discount_value(self):
        value = self.cleaned_data.get('discount_value')
        if value is None:
            raise forms.ValidationError("Discount value is required.")
        if value <= 0:
            raise forms.ValidationError("Discount value must be greater than 0.")
        return value

    def clean_min_amount(self):
        amount = self.cleaned_data.get('min_amount')
        if amount is not None and amount < 0:
            raise forms.ValidationError("Minimum purchase amount cannot be negative.")
        return amount

    def clean_max_discount(self):
        value = self.cleaned_data.get('max_discount')
        if value is not None and value <= 0:
            raise forms.ValidationError("Maximum discount must be greater than 0.")
        return value

    def clean_usage_limit(self):
        limit = self.cleaned_data.get('usage_limit')
        if limit is not None and limit < 1:
            raise forms.ValidationError("Usage limit must be at least 1.")
        return limit

    def clean_usage_limit_per_user(self):
        limit = self.cleaned_data.get('usage_limit_per_user')
        if limit is not None and limit < 1:
            raise forms.ValidationError("Per-user usage limit must be at least 1.")
        return limit

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        today = timezone.now().date()
        # Only enforce "not in the past" on CREATE
        if not self.instance.pk and start_date and start_date < today:
            raise forms.ValidationError("Start date cannot be in the past.")
        return start_date

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get('expiry_date')
        if not expiry_date:
            raise forms.ValidationError("Expiry date is required.")
        if expiry_date < timezone.now().date():
            raise forms.ValidationError("Expiry date cannot be in the past.")
        return expiry_date

    # ── Cross-field ───────────────────────────────────────────────

    def clean(self):
        cleaned = super().clean()
        discount_type  = cleaned.get('discount_type')
        discount_value = cleaned.get('discount_value')
        max_discount   = cleaned.get('max_discount')
        start_date     = cleaned.get('start_date')
        expiry_date    = cleaned.get('expiry_date')

        # Percentage cap
        if discount_type == 'percentage' and discount_value is not None:
            if discount_value > 100:
                self.add_error('discount_value',
                               "Percentage discount cannot exceed 100%.")

        # max_discount only valid for percentage
        if discount_type == 'fixed' and max_discount:
            self.add_error('max_discount',
                           "Maximum discount cap is only applicable to percentage coupons.")

        # Date range
        if start_date and expiry_date and expiry_date <= start_date:
            self.add_error('expiry_date',
                           "Expiry date must be after the start date.")

        return cleaned
