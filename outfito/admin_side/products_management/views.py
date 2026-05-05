from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import  Prefetch
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Product
from admin_side.variants_management.models import Variant
from admin_side.categories_management.models import Category
from django.db import transaction, IntegrityError
import  re
from decimal import Decimal, InvalidOperation
from .utils import generate_sku
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from .forms import ProductForm, VariantFormSet

def is_admin(user):
    return user.is_authenticated and user.is_staff

VALID_TYPES = ['shirt', 'pant', 'tees', 'shorts','coat']
VALID_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def product_list(request):
    search=request.GET.get('search', '').strip()
    category_id=request.GET.get('category', '')
    status=request.GET.get('status', '')
    products=Product.objects.filter(is_deleted=False).select_related('category')

    if search:
        products=products.filter(name__icontains=search)
    if category_id:
        products = products.filter(category_id=category_id)
    if status=='active':
        products=products.filter(is_listed=True)
    elif status=='inactive':
        products=products.filter(is_listed=False)

    products=products.order_by('-created_at').distinct()

    products=products.prefetch_related(
        Prefetch('variants',queryset=Variant.objects.filter(is_default=True),to_attr='default_variant'))

    paginator=Paginator(products, 5)
    page_number=request.GET.get('page')
    page_obj=paginator.get_page(page_number)

    for product in page_obj:
        dv=getattr(product, 'default_variant', [])
        product.display_variant=dv[0] if dv else product.variants.first()

    categories=Category.objects.filter(is_deleted=False)

    context={
        'products':page_obj,
        'categories':categories,
        'search':search,
        'selected_category':category_id,
        'selected_status':status,
    }

    return render(request,'admin/product_list.html', context)



@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def add_product(request):
    categories = Category.objects.filter(is_deleted=False, is_active=True)
    if request.method=='POST':
        form = ProductForm(request.POST, request.FILES)
        formset = VariantFormSet(request.POST, prefix='variants')

        image_cover= request.FILES.get('image_cover')
        image_side= request.FILES.get('image_side')
        image_back= request.FILES.get('image_back')

        custom_errors = []
        if not image_cover or not image_side or not image_back:
            custom_errors.append('Minimum 3 images required.')
        else:
            for img, label in [(image_cover, 'Cover'), (image_side, 'Side'), (image_back, 'Back')]:
                if img.size > MAX_IMAGE_SIZE:
                    custom_errors.append(f'{label} image too large.')
                if img.content_type not in ALLOWED_TYPES:
                    custom_errors.append(f'Invalid {label} image.')

        if form.is_valid() and formset.is_valid() and not custom_errors:
            try:
                with transaction.atomic():
                    product = form.save(commit=False)
                    product.image_side = image_side
                    product.image_back = image_back
                    product.is_listed = True
                    product.save()

                    variants = formset.save(commit=False)
                    is_first = True
                    for variant in variants:
                        variant.product = product
                        variant.color = form.cleaned_data.get('color')
                        variant.image = image_cover
                        variant.is_active = form.cleaned_data.get('is_listed', True)
                        variant.is_default = is_first
                        is_first = False
                        variant.sku = generate_sku(product, variant)
                        variant.save()
                    
                    messages.success(request, f'Product "{product.name}" added successfully.')
                    return redirect('product_list')

            except IntegrityError:
                custom_errors.append('Duplicate error.')
            except Exception as e:
                custom_errors.append(f'Error: {e}')

        for err in custom_errors:
            messages.error(request, err)

    else:
        form = ProductForm()
        formset = VariantFormSet(prefix='variants')

    return render(request, 'admin/add_product.html', {
        'form': form,
        'formset': formset,
        'categories': categories,
        'sizes': SIZES,
        'old': request.POST if request.method == 'POST' else None,
    })
 
@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def edit_product(request, pk):
    product=get_object_or_404(Product, pk=pk, is_deleted=False)
    categories=Category.objects.filter(is_deleted=False, is_active=True).order_by('category_name')
    
    first_variant=product.variants.first()
    initial_color=first_variant.color if first_variant else '#000000'

    if request.method=='POST':
        form=ProductForm(request.POST, request.FILES, instance=product)
        formset=VariantFormSet(request.POST, instance=product, prefix='variants')

        new_cover=request.FILES.get('image_cover')
        new_side=request.FILES.get('image_side')
        new_back=request.FILES.get('image_back')

        keep_cover=request.POST.get('keep_image_cover', '0') == '1'
        keep_side=request.POST.get('keep_image_side',  '0') == '1'
        keep_back=request.POST.get('keep_image_back',  '0') == '1'

        custom_errors = []
        for img_file, label in [(new_cover, 'Cover'), (new_side, 'Side'), (new_back, 'Back')]:
            if img_file:
                if img_file.size > MAX_IMAGE_SIZE:
                    custom_errors.append(f'{label} image must be under 5 MB.')
                elif img_file.content_type not in ALLOWED_TYPES:
                    custom_errors.append(f'{label} image: invalid type.')

        cover_ok = (keep_cover and first_variant and first_variant.image) or (new_cover is not None)
        if not cover_ok:
            custom_errors.append('Cover image is required.')

        if form.is_valid() and formset.is_valid() and not custom_errors:
            try:
                with transaction.atomic():
                    product = form.save(commit=False)
                    product.is_listed = form.cleaned_data.get('is_listed', True)
                    if new_side:
                        if product.image_side:
                            product.image_side.delete(save=False)
                        product.image_side = new_side
                    elif not keep_side:
                        if product.image_side:
                            product.image_side.delete(save=False)
                        product.image_side = None

                    if new_back:
                        if product.image_back:
                            product.image_back.delete(save=False)
                        product.image_back = new_back
                    elif not keep_back:
                        if product.image_back:
                            product.image_back.delete(save=False)
                        product.image_back = None

                    product.save()
                    variants = formset.save(commit=False)
                    for obj in formset.deleted_objects:
                        obj.delete()

                    is_first = True
                    for variant in variants:
                        variant.product = product
                        variant.color = form.cleaned_data['color']
                        
                        if new_cover:
                            variant.image = new_cover
                        elif not keep_cover:
                            variant.image = None
                        elif not variant.image and first_variant and first_variant.image:
                             variant.image = first_variant.image

                        variant.is_active = form.cleaned_data.get('is_listed', True)
                        variant.is_default = is_first
                        is_first = False

                        if not variant.sku:
                            variant.sku = generate_sku(product, variant)
                        
                        variant.save()

                messages.success(request, f'Product "{product.name}" updated successfully.')
                return redirect('product_list')

            except IntegrityError:
                custom_errors.append('Database error: possible duplicate SKU or data.')
            except Exception as e:
                custom_errors.append(f'Error updating: {str(e)}')

        for err in custom_errors:
            messages.error(request, err)

    else:
        form = ProductForm(instance=product, initial={'color': initial_color})
        formset = VariantFormSet(instance=product, prefix='variants')

    return render(request, 'admin/edit_product.html', {
        'product': product,
        'variant': first_variant,
        'form': form,
        'formset': formset,
        'categories': categories,
        'sizes': SIZES,
        'old': request.POST if request.method == 'POST' else None,
    })

def archive_product(request, pk):
    product=get_object_or_404(Product, pk=pk)
    if request.method=='POST':
        name = product.name
        product.is_deleted=True
        product.archived_at=timezone.now()
        product.save(update_fields=['is_deleted', 'archived_at'])
        messages.success(request, f'Product "{name}" has been archived.')
        return redirect('product_list')

    return redirect('edit_product', pk=pk)

@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def restore_product(request, pk):
    product=get_object_or_404(Product, pk=pk, is_deleted=True)
    if request.method=='POST':
        name = product.name
        product.is_deleted=False
        product.archived_at=None
        product.save(update_fields=['is_deleted', 'archived_at'])
        messages.success(request, f'Product "{name}" has been restored successfully.')
    return redirect('archived_product_list')

@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def archived_product_list(request):
    search=request.GET.get('search', '').strip()
    category_id=request.GET.get('category', '')
    products=Product.objects.filter(is_deleted=True).select_related('category')

    if search:
        products=products.filter(name__icontains=search)
    if category_id:
        products = products.filter(category_id=category_id)

    products=products.order_by('-archived_at', '-created_at').distinct()

    products=products.prefetch_related(
        Prefetch('variants',queryset=Variant.objects.filter(is_default=True),to_attr='default_variant'))

    paginator=Paginator(products, 10)
    page_number=request.GET.get('page')
    page_obj=paginator.get_page(page_number)

    for product in page_obj:
        dv=getattr(product, 'default_variant', [])
        product.display_variant=dv[0] if dv else product.variants.first()

    categories=Category.objects.filter(is_deleted=False)

    context={
        'products':page_obj,
        'categories':categories,
        'search':search,
        'selected_category':category_id,
    }

    return render(request,'admin/archived_product_list.html', context)


def toggle_product_status(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_listed = not product.is_listed
    product.save()
    
    # Check referer to redirect back to the correct list
    referer = request.META.get('HTTP_REFERER', '')
    if 'archived' in referer:
        return redirect('archived_product_list')
    return redirect('product_list')