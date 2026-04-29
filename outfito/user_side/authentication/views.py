from django.shortcuts import render, redirect
from .models import OTP
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.conf import settings
from django.utils import timezone
from admin_side.categories_management.models import Category
from admin_side.products_management.models import Product
from admin_side.variants_management.models import Variant
from django.db.models import Prefetch
from .referral_utils import assign_referral


@never_cache
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('landing')

    ref_code = (request.GET.get('ref', '').strip().upper() or request.session.get('ref_code', ''))
    if ref_code:
        request.session['ref_code']=ref_code

    if request.method=="POST":
        uname=request.POST.get('username', '')
        email=request.POST.get('email', '')
        pass1=request.POST.get('password1', '')
        pass2=request.POST.get('password2', '')
        form_ref=request.POST.get('referral_code', '').strip().upper()
        if form_ref:
            request.session['ref_code'] = form_ref

        # Helper to re-render with values preserved
        def form_error(msg):
            messages.error(request, msg)
            return render(request, 'user/signup.html', {
                'prefilled_ref': form_ref or ref_code,
                'form_username': uname,
                'form_email': email,
            })

        if not uname:
            return form_error("Username is required")

        if uname.isdigit():
            return form_error("Username cannot contain only numbers")

        if not re.match(r'^[A-Za-z0-9_ ]+$', uname):
            return form_error("Username can contain letters, numbers and underscore")

        if not email:
            return form_error("Email is required")

        try:
            validate_email(email)
        except ValidationError:
            return form_error("Enter a valid email address")

        if not pass1 or not pass2:
            return form_error("Password fields cannot be empty")

        if pass1 != pass2:
            return form_error("Passwords do not match")

        if len(pass1) < 8:
            return form_error("Password must be at least 8 characters")

        if not re.search(r'[A-Z]', pass1):
            return form_error("Password must contain at least one uppercase letter")

        if not re.search(r'[a-z]', pass1):
            return form_error("Password must contain at least one lowercase letter")

        if not re.search(r'[0-9]', pass1):
            return form_error("Password must contain at least one number")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', pass1):
            return form_error("Password must contain at least one special character")

        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            if existing_user.is_verified:
                return form_error("Email already registered")
            else:
                existing_user.delete()

        if User.objects.filter(username=uname).exists():
            return form_error("Username already exists")

        user = User.objects.create_user(
            username=uname,
            email=email,
            password=pass1
        )

        user.is_active = False
        user.is_verified = False
        user.save()

        request.session['email'] = user.email

        OTP.objects.filter(user=user).delete()
        otp = OTP.objects.create(user=user)

        otp_expires_in = max(1, round((otp.expired_at - timezone.now()).total_seconds() / 60)) if otp.expired_at else 1
        html_msg = render_to_string('user/otp_email.html', {
            'otp': otp.code,
            'user_name': user.username,
            'otp_expires_in': otp_expires_in,
        })
        send_mail(
            subject='Your OTP Code',
            message=f'Hello {user.username},\n\nYour OTP is {otp.code}\nIt expires in {otp_expires_in} minute{"s" if otp_expires_in != 1 else ""}.',
            from_email='outfito0848@gmail.com',
            recipient_list=[user.email],
            fail_silently=False,
            html_message=html_msg,
        )

        messages.success(request, "OTP sent to your email")
        return redirect('otp_verify')

    return render(request, 'user/signup.html', {'prefilled_ref': ref_code})

@never_cache
def otp_verify(request):

    email = request.session.get('email')

    if not email:
        return redirect('signup')

    user = User.objects.filter(email=email).first()

    if not user:
        return redirect('signup')

    otp, remaining_seconds = get_otp_timer(user)

    if request.method == 'POST':

        code = request.POST.get('otp')

        if not otp:
            messages.error(request, "OTP not found")
            return redirect('otp_verify')

        if otp.is_expired():
            otp.delete()
            messages.error(request, "OTP expired. Please resend.")
            return redirect('otp_verify')

        if str(otp.code) != str(code):
            messages.error(request, "Invalid OTP")
            return redirect('otp_verify')

        user.is_active   = True
        user.is_verified = True
        user.save()

        otp.delete()

        ref_code = request.session.pop('ref_code', None)
        referral_applied = False
        if ref_code:
            referral_applied = assign_referral(user, ref_code)

        request.session.pop('email', None)

        if referral_applied:
            messages.success(request, f"Referral code '{ref_code}' applied! Complete your first order to earn Ã¢â€šÂ¹50.")
        else:
            messages.success(request, "Email verified successfully")

        return redirect('login')

    return render(request, 'user/otp_verify.html', {'email': email,'remaining_seconds': remaining_seconds})


def get_otp_timer(user):
    otp=OTP.objects.filter(user=user).last()
    remaining_seconds=0
    if otp:
        remaining_seconds = int((otp.expired_at - timezone.now()).total_seconds())
        if remaining_seconds < 0:
            remaining_seconds = 0

    return otp, remaining_seconds


@never_cache
def resend_signup_otp(request):

    email = request.session.get("email")

    if not email:
        return redirect("signup")

    user = User.objects.filter(email=email).first()

    if not user:
        return redirect("signup")

    otp, remaining_seconds = get_otp_timer(user)

    if otp and remaining_seconds > 0:
        messages.error(request,f"Please wait {remaining_seconds}s before requesting a new OTP.")
        return redirect("otp_verify")

    OTP.objects.filter(user=user).delete()

    otp = OTP.objects.create(user=user)

    html_msg = render_to_string('user/otp_email.html', {'otp': otp.code, 'user_name': user.username, 'otp_expires_in': max(1, round((otp.expired_at - timezone.now()).total_seconds() / 60)) if otp.expired_at else 1})
    send_mail(
        subject="Signup OTP",
        message=f"Your OTP is {otp.code}",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_msg,
    )

    messages.success(request,"New OTP sent successfully")

    return redirect("otp_verify")


@never_cache
def resend_reset_otp(request):

    email = request.session.get("reset_email")

    if not email:
        return redirect("forgot_password")

    user = User.objects.filter(email=email).first()

    if not user:
        return redirect("forgot_password")

    otp, remaining_seconds = get_otp_timer(user)

    if otp and remaining_seconds > 0:
        messages.error(request,f"Please wait {remaining_seconds}s before requesting a new OTP.")
        return redirect("reset_verify")

    OTP.objects.filter(user=user).delete()

    otp = OTP.objects.create(user=user)

    html_msg = render_to_string('user/otp_email.html', {'otp': otp.code, 'user_name': user.username, 'otp_expires_in': max(1, round((otp.expired_at - timezone.now()).total_seconds() / 60)) if otp.expired_at else 1})
    send_mail(
        subject="Password Reset OTP",
        message=f"Your OTP is {otp.code}",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_msg,
    )

    messages.success(request,"New OTP sent successfully")

    return redirect("reset_verify")

@never_cache
def change_email(request):
    request.session.pop('email', None)
    messages.info(request, "Please enter new email.")
    return redirect('login')


@never_cache
def login_view(request):

    if request.user.is_authenticated:
        return redirect('landing')

    if request.method == 'POST':

        email = request.POST.get('email', '')
        password = request.POST.get('password', '')

        def login_error(msg, level='error'):
            if level == 'warning':
                messages.warning(request, msg)
            else:
                messages.error(request, msg)
            return render(request, 'user/login.html', {'form_email': email})

        user = User.objects.filter(email=email).first()

        if not user:
            return login_error("Invalid email or password")

        if not user.is_active:
            return login_error("Your account is blocked. Contact support.")

        if not user.is_verified:
            return login_error("Please verify your email first.", level='warning')

        user = authenticate(request, email=email, password=password)

        if user is None:
            return login_error("Invalid email or password")

        login(request, user)
        messages.success(request, "Login successful!")
        return redirect('landing')

    return render(request, 'user/login.html')


@never_cache
def forgot_password(request):
    
    if request.user.is_authenticated:
        return redirect('landing')

    if request.method == "POST":

        email = request.POST.get("email")

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request,"No account found with this email.")
            return render(request,"user/forgot_password.html")

        request.session["reset_email"] = email

        OTP.objects.filter(user=user).delete()

        otp = OTP.objects.create(user=user)

        html_msg = render_to_string('user/otp_email.html', {'otp': otp.code, 'user_name': user.username, 'otp_expires_in': max(1, round((otp.expired_at - timezone.now()).total_seconds() / 60)) if otp.expired_at else 1})
        send_mail(
            subject="Password Reset OTP",
            message=f"Your OTP is {otp.code}",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email],
            fail_silently=False,
            html_message=html_msg,
        )

        return redirect("reset_verify")

    return render(request,"user/forgot_password.html")

@never_cache
def back_to_login(request):
    request.session.pop('reset_email', None)
    return redirect('login')


@never_cache
def reset_verify(request):

    email = request.session.get('reset_email')

    if not email:
        return redirect('login')

    user = User.objects.filter(email=email).first()

    if not user:
        return redirect('login')

    otp, remaining_seconds = get_otp_timer(user)

    if request.method == 'POST':

        code = request.POST.get('otp')

        if not otp:
            messages.error(request, "OTP not found")
            return redirect('reset_verify')

        if otp.is_expired():
            otp.delete()
            messages.error(request, "OTP expired. Please resend.")
            return redirect('reset_verify')

        if str(otp.code) != str(code):
            messages.error(request, "Invalid OTP")
            return redirect('reset_verify')

        otp.delete()

        request.session['otp_verified'] = True

        return redirect('set_new_password')

    return render(request, 'user/reset_verify.html', {
        'email': email,
        'remaining_seconds': remaining_seconds
    })


@never_cache
def set_new_password(request):

    email = request.session.get('reset_email')
    verified = request.session.get('otp_verified')

    if not email or not verified:
        messages.error(request, "Unauthorized access")
        return redirect('login')

    if request.method == "POST":

        pass1 = request.POST.get('password1')
        pass2 = request.POST.get('password2')

        if not pass1 or not pass2:
            messages.error(request, "Password fields cannot be empty")
            return redirect('set_new_password')

        if pass1 != pass2:
            messages.error(request, "Passwords do not match")
            return redirect('set_new_password')

        if len(pass1) < 8:
            messages.error(request, "Password must be at least 8 characters")
            return redirect('set_new_password')

        if not re.search(r'[A-Z]', pass1):
            messages.error(request, "Must contain at least 1 uppercase letter")
            return redirect('set_new_password')

        if not re.search(r'[a-z]', pass1):
            messages.error(request, "Must contain at least 1 lowercase letter")
            return redirect('set_new_password')

        if not re.search(r'[0-9]', pass1):
            messages.error(request, "Must contain at least 1 number")
            return redirect('set_new_password')

        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', pass1):
            messages.error(request, "Must contain at least 1 special character")
            return redirect('set_new_password')

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request, "User not found")
            return redirect('login')

        if check_password(pass1, user.password):
            messages.error(request, "New password cannot be the same as the old password")
            return redirect('set_new_password')

        user.password = make_password(pass1)
        user.save()

        request.session.flush()

        messages.success(request, "Password reset successful")
        return redirect('login')

    return render(request, 'user/set_new_password.html')


@never_cache
def landing_view(request):

    categories = Category.objects.filter(
        is_deleted=False
    ).order_by('-created_at')[:3]

    variant_qs = Variant.objects.filter(is_active=True)

    # Ã¢Å“â€¦ get all valid products
    all_products = Product.objects.filter(
        is_deleted=False,
        is_listed=True
    ).prefetch_related(
        Prefetch('variants', queryset=variant_qs, to_attr='active_variants')
    ).order_by('-created_at')

    # Ã¢Å“â€¦ split for Velour UI
    hero_products = all_products[:4]
    grid_products = all_products[4:]

    # Ã¢Å“â€¦ marquee fix
    marquee_items = [
        "New Arrivals",
        "The Vault Collection",
        "SS 2026",
        "Limited Edition Pieces",
        "Free Worldwide Shipping",
    ]

    context = {
        'categories': categories,
        'hero_products': hero_products,
        'grid_products': grid_products,
        'marquee_items': marquee_items,
    }

    return render(request, 'user/landing.html', context)

@never_cache    
def logout_view(request):
   logout(request)
   return redirect('landing')




