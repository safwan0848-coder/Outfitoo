from django.shortcuts import render,redirect
from .forms import SignupForm,ResetPasswordForm
from .models import OTP
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth import authenticate, login,logout
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


def signup_view(request):
    if request.method == 'POST':
        form=SignupForm(request.POST)
        if form.is_valid():
            user=form.save(commit=False)
            user.is_active=False
            user.is_verified=False
            user.save()

            request.session['email']=user.email

            OTP.objects.filter(user=user).delete()
            otp=OTP.objects.create(user=user)

            send_mail(
                subject='Your OTP Code',
                message=f'Hello {user.username},\n\nYour OTP is {otp.code}\nIt expires in 5 minutes.',
                from_email='outfito0848@gmail.com',
                recipient_list=[user.email],
                fail_silently=False,
            )

            return redirect('otp_verify')

        return render(request, 'user/signup.html', {'form': form})
    return render(request, 'user/signup.html', {'form': SignupForm()})

from django.utils import timezone

def otp_verify(request):

    email = request.session.get('email')
    if not email:
        return redirect('signup')

    user = User.objects.filter(email=email).first()
    otp = OTP.objects.filter(user=user).last()

    remaining_seconds = 0
    if otp:
        remaining_seconds = int((otp.expired_at - timezone.now()).total_seconds())
        if remaining_seconds < 0:
            remaining_seconds = 0

    if request.method == 'POST':
        code = request.POST.get('otp')

        if not otp:
            messages.error(request, "OTP not found")
            return redirect('otp_verify')

        if otp.is_expired():
            otp.delete()
            messages.error(request, "OTP expired. Please resend.")
            return redirect('otp_verify')

        if otp.code != code:
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
        

def resend_otp(request):
    email=request.session.get('email')
    if not email:
        return redirect('signup')
    user=User.objects.filter(email=email).first()
    if not user:
        return redirect('signup')
    OTP.objects.filter(user=user).delete()

    otp=OTP.objects.create(user=user)
    send_mail(
        subject='Resend OTP',
        message=f'Your new OTP is {otp.code}',
        from_email='outfito0848@gmail.com',
        recipient_list=[user.email],
        fail_silently=False,
    )
    messages.success(request, "New OTP sent successfully")
    return redirect('otp_verify')

def change_email(request):
    request.session.pop('email', None)
    messages.info(request, "Please enter new email.")
    return redirect('signup')

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages

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

    if request.method == 'POST':
        email = request.POST.get('email')

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request, "No account found with this email.")
            return render(request, 'user/forgot_password.html')

        request.session['reset_email'] = email

        OTP.objects.filter(user=user).delete()

        otp = OTP.objects.create(
            user=user,
            code=OTP.generate_otp()
        )

        send_mail(
            subject="Password Reset OTP",
            message=f"Your OTP is {otp.code}",
            from_email="outfito0848@gmail.com",
            recipient_list=[user.email],
            fail_silently=False,
        )

        return redirect('reset_verify')

    return render(request, 'user/forgot_password.html')


def back_to_login(request):
    request.session.pop('reset_email', None)
    return redirect('login')


def reset_verify(request):

    email = request.session.get('reset_email')
    if not email:
        return redirect('login')

    user = User.objects.filter(email=email).first()
    otp = OTP.objects.filter(user=user).last()

    remaining_seconds = 0
    if otp:
        remaining_seconds = int((otp.expired_at - timezone.now()).total_seconds())
        if remaining_seconds < 0:
            remaining_seconds = 0

    if request.method == 'POST':
        code = request.POST.get('otp')

        if not otp:
            messages.error(request, "OTP not found")
            return redirect('reset_verify')

        if otp.is_expired():
            otp.delete()
            messages.error(request, "OTP expired. Please resend.")
            return redirect('reset_verify')

        if otp.code != code:
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
        return redirect('login')

    form = ResetPasswordForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = User.objects.filter(email=email).first()
            user.password = make_password(form.cleaned_data['password1'])
            user.save()

            request.session.flush()
            messages.success(request, "Password reset successful.")
            return redirect('login')

    return render(request, 'user/set_new_password.html', {'form': form})


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
