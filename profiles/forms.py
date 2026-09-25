from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm

from profiles.models import Profile


class UserUpdateForm(forms.ModelForm):
    field_settings = {
        'first_name': ('Nome', 'Seu nome'),
        'last_name': ('Sobrenome', 'Seu sobrenome'),
    }

    class Meta:
        model = get_user_model()
        fields = ('first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, (label, placeholder) in self.field_settings.items():
            field = self.fields[name]
            field.required = True
            field.label = label
            field.widget.attrs.update(
                {'class': 'input', 'placeholder': placeholder}
            )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('phone', 'birth_date')
        labels = {
            'phone': 'Telefone',
            'birth_date': 'Data de nascimento',
        }
        widgets = {
            'phone': forms.TextInput(
                attrs={'class': 'input', 'placeholder': '(00) 00000-0000'}
            ),
            'birth_date': forms.DateInput(
                attrs={'class': 'input', 'type': 'date'},
                format='%Y-%m-%d',
            ),
        }


class StyledPasswordChangeForm(PasswordChangeForm):
    field_labels = {
        'old_password': 'Senha atual',
        'new_password1': 'Nova senha',
        'new_password2': 'Confirmar nova senha',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.label = self.field_labels.get(name, field.label)
            field.widget.attrs.update({'class': 'input'})
