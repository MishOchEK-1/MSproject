from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import slugify

from .models import User, UserRole


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Пароль', strip=False, widget=forms.PasswordInput)

    error_messages = {
        'invalid_login': 'Неверный email или пароль.',
        'inactive': 'Учетная запись отключена.',
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    self.error_messages['inactive'],
                    code='inactive',
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache


class UserRegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            'full_name',
            'email',
            'phone',
            'organization',
            'visit_purpose',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organization'].required = False
        self.fields['visit_purpose'].required = False
        self.fields['full_name'].widget.attrs.update({'placeholder': 'Иванов Иван Иванович'})
        self.fields['email'].widget.attrs.update({'placeholder': 'you@example.com'})
        self.fields['phone'].widget.attrs.update({'placeholder': '+7XXXXXXXXXX'})
        self.fields['organization'].widget.attrs.update({'placeholder': 'Если вы гость'})
        self.fields['visit_purpose'].widget.attrs.update({'rows': 4})

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = UserRole.GUEST
        user.username = self._build_unique_username()
        if commit:
            user.save()
        return user

    def _build_unique_username(self):
        email = self.cleaned_data['email']
        base = slugify(email.split('@')[0]) or 'user'
        username = base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{base}-{suffix}'
        return username


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('full_name', 'email', 'phone', 'organization', 'visit_purpose')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        existing = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email


class UserTrainingStatusForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('has_completed_training',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['has_completed_training'].label = 'Инструктаж пройден'
