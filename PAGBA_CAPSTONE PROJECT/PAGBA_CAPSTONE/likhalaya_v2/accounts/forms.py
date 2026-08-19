import re
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=50)
    last_name = forms.CharField(max_length=50)
    agree_terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must agree to the Terms of Service.'}
    )

    class Meta:
        model = CustomUser
        # Username is intentionally not part of the visible signup form —
        # it's auto-generated from the email address in save() below so
        # the model's (still-required) username field is populated without
        # asking the user to pick one.
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']

    def _generate_username(self, email):
        base = re.sub(r'[^a-zA-Z0-9._]', '', email.split('@')[0]) or 'user'
        base = base[:25] or 'user'
        # Same "abandoned, never-verified signup" cleanup as before, just
        # keyed on the generated candidate instead of a user-typed value.
        CustomUser.all_objects.filter(username=base, is_active=False).delete()
        candidate = base
        suffix = 0
        while CustomUser.all_objects.filter(username=candidate, is_active=True).exists():
            suffix += 1
            candidate = f'{base}{suffix}'
        return candidate

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Clear out any abandoned, never-verified signup that used this email
        # (e.g. someone who registered, saw the OTP page, then hit Back).
        CustomUser.all_objects.filter(email=email, is_active=False).delete()
        if CustomUser.all_objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError('An account with that email already exists.')
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'agree_terms':
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({'class': 'form-control'})
        # By default Django clears password fields whenever the form is
        # re-rendered after a validation error (e.g. unchecked Terms of
        # Service). Keep the typed values so the user doesn't have to
        # re-type their password every time.
        self.fields['password1'].widget.render_value = True
        self.fields['password2'].widget.render_value = True

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self._generate_username(self.cleaned_data['email'])
        if commit:
            user.save()
        return user

class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'style': 'letter-spacing:8px;font-size:24px;font-weight:700;',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'placeholder': '------',
        })
    )


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'barangay', 'city', 'province', 'zip_code', 'avatar']
        widgets = {
            'address': forms.TextInput(attrs={'placeholder': 'House #, Street'}),
            'avatar': forms.FileInput(),
            'province': forms.HiddenInput(),
            'city': forms.HiddenInput(),
            'barangay': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})