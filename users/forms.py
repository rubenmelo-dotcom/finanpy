from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from core.forms import PasswordErrorsOnFirstFieldMixin, StyledFormMixin
from users.models import User


class SignUpForm(
    StyledFormMixin, PasswordErrorsOnFirstFieldMixin, UserCreationForm
):
    field_settings = {
        'first_name': ('Nome', 'Seu nome'),
        'last_name': ('Sobrenome', 'Seu sobrenome'),
        'email': ('E-mail', 'voce@exemplo.com'),
        'password1': ('Senha', 'Crie uma senha'),
        'password2': ('Confirmar senha', 'Repita a senha'),
    }

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        for name, (label, placeholder) in self.field_settings.items():
            field = self.fields[name]
            field.label = label
            field.widget.attrs.update(
                {'class': 'input', 'placeholder': placeholder}
            )

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data.get('email'))
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'Já existe uma conta com este e-mail.',
                code='unique',
            )
        return email


class LoginForm(StyledFormMixin, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'E-mail ou senha inválidos.',
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields['username'].label = 'E-mail'
        self.fields['username'].widget.attrs.update(
            {'class': 'input', 'placeholder': 'voce@exemplo.com'}
        )
        self.fields['password'].label = 'Senha'
        self.fields['password'].widget.attrs.update(
            {'class': 'input', 'placeholder': 'Sua senha'}
        )
