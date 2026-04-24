from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import Product
from admin_side.variants_management.models import Variant
from admin_side.categories_management.models import Category
import re

class ProductForm(forms.ModelForm):
    color = forms.CharField(max_length=50, required=True)
    image_cover = forms.ImageField(required=False)
    
    class Meta:
        model = Product
        fields = ['name', 'description', 'category', 'product_type', 'is_listed', 'image_side', 'image_back']

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if len(name) < 7:
            raise forms.ValidationError("Product name must be at least 7 characters.")
        if not re.match(r"^[A-Za-z0-9\s\-\']+$", name):
            raise forms.ValidationError("Product name contains invalid characters.")
        return name

    def clean_color(self):
        color = self.cleaned_data.get('color')
        if not color or not re.match(r"^([A-Za-z\s]+|#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}))$", color):
            raise forms.ValidationError("Invalid color. Use valid hex or letters.")
        return color.title()


class VariantForm(forms.ModelForm):
    class Meta:
        model = Variant
        fields = ['size', 'price', 'stock']

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is None or price <= 0:
            raise forms.ValidationError("Price must be greater than 0.")
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is None or stock < 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock


class BaseVariantFormSet(BaseInlineFormSet):
    def clean(self):
        if any(self.errors):
            return
        
        sizes = []
        has_variant = False
        
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
                
            size = form.cleaned_data.get('size')
            if size:
                has_variant = True
                if size in sizes:
                    raise forms.ValidationError(f"Duplicate size selected: {size}")
                sizes.append(size)
                
        if not has_variant:
            raise forms.ValidationError("At least one variant (size) is required.")

VariantFormSet = inlineformset_factory(
    Product, Variant,
    form=VariantForm,
    formset=BaseVariantFormSet,
    extra=0,
    can_delete=True
)
