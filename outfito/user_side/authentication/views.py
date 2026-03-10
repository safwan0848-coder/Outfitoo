from django.shortcuts import render,redirect
from .models import OTP
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth import authenticate, login,logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password,check_password
from django.views.decorators.cache import never_cache
import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.conf import settings

def signup_view(request):

    if request.method == "POST":

        uname = request.POST.get('username')
        email = request.POST.get('email')
        pass1 = request.POST.get('password1')
        pass2 = request.POST.get('password2')

        # Username required
        if not uname:
            messages.error(request, "Username is required")
            return redirect('signup')

        # Username cannot be only numbers
        if uname.isdigit():
            messages.error(request, "Username cannot contain only numbers")
            return redirect('signup')

        # Username regex validation
        if not re.match(r'^[A-Za-z0-9]+$', uname):
            messages.error(
                request,
                "Username can contain only letters and numbers"
            )
            return redirect('signup')

        # Email required
        if not email:
            messages.error(request, "Email is required")
            return redirect('signup')

        # Email validation
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter a valid email address")
            return redirect('signup')

        # Password empty check
        if not pass1 or not pass2:
            messages.error(request, "Password fields cannot be empty")
            return redirect('signup')

        # Password length
        if len(pass1) < 6:
            messages.error(request, "Password must be at least 6 characters")
            return redirect('signup')

        # Password match
        if pass1 != pass2:
            messages.error(request, "Password and Confirm Password are not the same")
            return redirect('signup')

        # Username exists
        if User.objects.filter(username=uname).exists():
            messages.error(request, "Username already exists")
            return redirect('signup')

        # Email exists
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect('signup')

        # Create user
        user = User.objects.create_user(
            username=uname,
            email=email,
            password=pass1
        )

        user.is_active = False
        user.is_verified = False
        user.save()

        # Save email in session
        request.session['email'] = user.email

        # Generate OTP
        OTP.objects.filter(user=user).delete()
        otp = OTP.objects.create(user=user)

        # Send OTP Email
        send_mail(
            subject='Your OTP Code',
            message=f'Hello {user.username},\n\nYour OTP is {otp.code}\nIt expires in 5 minutes.',
            from_email='outfito0848@gmail.com',
            recipient_list=[user.email],
            fail_silently=False,
        )

        messages.success(request, "OTP sent to your email")
        return redirect('otp_verify')

    return render(request, 'user/signup.html')

from django.utils import timezone

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

        user.is_active = True
        user.is_verified = True
        user.save()

        otp.delete()

        request.session.pop('email', None)

        messages.success(request, "Email verified successfully")

        return redirect('login')

    return render(request, 'user/otp_verify.html', {
        'email': email,
        'remaining_seconds': remaining_seconds
    })


def get_otp_timer(user):

    otp = OTP.objects.filter(user=user).last()

    remaining_seconds = 0

    if otp:
        remaining_seconds = int((otp.expired_at - timezone.now()).total_seconds())

        if remaining_seconds < 0:
            remaining_seconds = 0

    return otp, remaining_seconds


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

    send_mail(
        subject="Signup OTP",
        message=f"Your OTP is {otp.code}",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[user.email],
        fail_silently=False
    )

    messages.success(request,"New OTP sent successfully")

    return redirect("otp_verify")


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

    send_mail(
        subject="Password Reset OTP",
        message=f"Your OTP is {otp.code}",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[user.email],
        fail_silently=False
    )

    messages.success(request,"New OTP sent successfully")

    return redirect("reset_verify")


def change_email(request):
    request.session.pop('email', None)
    messages.info(request, "Please enter new email.")
    return redirect('signup')


@never_cache
def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, email=email, password=password)

        if user is None:
            messages.error(request, "Invalid email or password")
            return render(request, 'user/login.html')

        if user.is_blocked:
            messages.error(request, "Your account is blocked. Contact support.")
            return render(request, 'user/login.html')

        if not user.is_verified:
            messages.warning(request, "Please verify your email first.")
            return render(request, 'user/login.html')

        if not user.is_active:
            messages.error(request, "Your account is not active.")
            return render(request, 'user/login.html')

        login(request, user)
        messages.success(request, "Login successful!")
        return redirect('landing')

    return render(request, 'user/login.html')


def forgot_password(request):

    if request.method == "POST":

        email = request.POST.get("email")

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request,"No account found with this email.")
            return render(request,"user/forgot_password.html")

        # store email in session
        request.session["reset_email"] = email

        OTP.objects.filter(user=user).delete()

        otp = OTP.objects.create(user=user)

        send_mail(
            subject="Password Reset OTP",
            message=f"Your OTP is {otp.code}",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email],
            fail_silently=False
        )

        return redirect("reset_verify")

    return render(request,"user/forgot_password.html")

def back_to_login(request):
    request.session.pop('reset_email', None)
    return redirect('login')


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

        if len(pass1) < 6:
            messages.error(request, "Password must be at least 6 characters")
            return redirect('set_new_password')

        if pass1 != pass2:
            messages.error(request, "Passwords do not match")
            return redirect('set_new_password')

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request, "User not found")
            return redirect('login')

        # 🔴 Prevent same password reuse
        if check_password(pass1, user.password):
            messages.error(request, "New password cannot be the same as the old password")
            return redirect('set_new_password')

        user.password = make_password(pass1)
        user.save()

        request.session.flush()

        messages.success(request, "Password reset successful")
        return redirect('login')

    return render(request, 'user/set_new_password.html')

def landing_view(request):
    return render (request,'user/landing.html')
    
def logout_view(request):
   logout(request)
   return redirect('landing')



def address(request):
    return HttpResponse('address')
def wallet(request):
    return HttpResponse('wallet')
def orders(request):
    return HttpResponse('orders')
