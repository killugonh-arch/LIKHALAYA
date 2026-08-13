from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .forms import RegisterForm, LoginForm, ProfileUpdateForm, OTPVerifyForm
from .models import CustomUser, EmailOTP


def _send_otp_email(user, otp):
    subject = 'One more step to confirm your account'
    context = {
        'first_name': user.first_name or user.username,
        'full_name': (f"{user.first_name} {user.last_name}".strip() or user.username),
        'code': otp.code,
        'valid_minutes': EmailOTP.OTP_VALID_MINUTES,
    }
    html_body = render_to_string('accounts/emails/otp_email.html', context)
    text_body = strip_tags(html_body)

    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)


def register_view(request):
    if request.user.is_authenticated:
        return redirect('store:home')
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # locked out until the emailed code is confirmed
            user.save()
            otp = EmailOTP.generate_for_user(user)
            try:
                _send_otp_email(user, otp)
            except Exception:
                messages.error(request, "We couldn't send the verification email. Please try again or contact support.")
                user.delete()
                return render(request, 'accounts/register.html', {'form': form, 'next': next_url})
            request.session['pending_verification_user_id'] = user.id
            request.session['pending_verification_next'] = next_url
            messages.info(request, f"We sent a 6-digit code to {user.email}. Enter it below to finish creating your account.")
            return redirect('accounts:verify_email')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form, 'next': next_url})


def verify_email_view(request):
    if request.user.is_authenticated:
        return redirect('store:home')
    user_id = request.session.get('pending_verification_user_id')
    if not user_id:
        messages.error(request, 'Nothing to verify. Please register first.')
        return redirect('accounts:register')
    user = get_object_or_404(CustomUser.all_objects, id=user_id, is_active=False)
    next_url = request.session.get('pending_verification_next', '')

    if request.method == 'POST':
        if 'resend' in request.POST:
            otp = EmailOTP.generate_for_user(user)
            try:
                _send_otp_email(user, otp)
                messages.success(request, f'A new code was sent to {user.email}.')
            except Exception:
                messages.error(request, "Couldn't resend the email. Please try again shortly.")
            return redirect('accounts:verify_email')

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            otp = EmailOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
            if not otp or not otp.is_valid():
                messages.error(request, 'That code has expired or is no longer valid. Please request a new one.')
            elif otp.code != code:
                otp.attempts += 1
                otp.save(update_fields=['attempts'])
                messages.error(request, 'Incorrect code. Please check your email and try again.')
            else:
                otp.is_used = True
                otp.save(update_fields=['is_used'])
                user.is_active = True
                user.save(update_fields=['is_active'])
                login(request, user)
                del request.session['pending_verification_user_id']
                request.session.pop('pending_verification_next', None)
                messages.success(request, f'Welcome to Likhalaya, {user.first_name or user.username}! Your email is verified.')
                if next_url:
                    return redirect(next_url)
                return redirect('store:home')
    else:
        form = OTPVerifyForm()
    return render(request, 'accounts/verify_email.html', {'form': form, 'email': user.email})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('store:home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            next_url = request.GET.get('next', '')
            if next_url:
                return redirect(next_url)
            if user.is_staff_user():
                return redirect('dashboard:home')
            return redirect('store:home')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('store:home')


@login_required
def profile_view(request):
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            if next_url:
                return redirect(next_url)
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    from orders.models import Order
    recent_orders = Order.objects.filter(user=request.user).prefetch_related('items')[:5]
    needs_contact_info = not request.user.phone or not request.user.address or not request.user.city or not request.user.province
    force_edit = request.GET.get('edit') == '1'
    show_edit = needs_contact_info or bool(next_url) or force_edit
    return render(request, 'accounts/profile.html', {
        'form': form,
        'recent_orders': recent_orders,
        'next': next_url,
        'needs_contact_info': needs_contact_info,
        'show_edit': show_edit,
    })


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
    for f in form.fields.values():
        f.widget.attrs.update({'class': 'form-control'})
    return render(request, 'accounts/change_password.html', {'form': form})