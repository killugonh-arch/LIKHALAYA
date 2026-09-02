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
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # If a previous signup attempt used this username but never verified
        # its email (is_active=False), it was abandoned — clear it out so
        # the person isn't permanently blocked from using their own username.
        CustomUser.all_objects.filter(username=username, is_active=False).delete()
        if CustomUser.all_objects.filter(username=username, is_active=True).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return username

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
    username = forms.CharField(
        label='Username or Email',
        widget=forms.TextInput(attrs={'autofocus': True}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Please enter a correct username/email and password. Note that both fields may be case-sensitive.',
    }

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