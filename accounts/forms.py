from django import forms

from accounts.models import Account


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = (
            'name',
            'bank_name',
            'account_type',
            'initial_balance',
            'is_active',
        )
        labels = {
            'name': 'Nome',
            'bank_name': 'Banco/instituição',
            'account_type': 'Tipo',
            'initial_balance': 'Saldo inicial',
            'is_active': 'Conta ativa',
        }
        help_texts = {
            'initial_balance': 'Saldo da conta no momento do cadastro.',
        }
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'input', 'placeholder': 'Ex.: Conta principal'}
            ),
            'bank_name': forms.TextInput(
                attrs={'class': 'input', 'placeholder': 'Ex.: Nubank'}
            ),
            'account_type': forms.Select(attrs={'class': 'input'}),
            'initial_balance': forms.NumberInput(
                attrs={
                    'class': 'input',
                    'step': '0.01',
                    'placeholder': '0,00',
                }
            ),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }
