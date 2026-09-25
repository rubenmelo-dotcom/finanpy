from django import forms
from django.db.models import Q

from accounts.models import Account
from categories.models import Category
from transactions.models import Transaction


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = (
            'transaction_type',
            'description',
            'amount',
            'date',
            'account',
            'category',
        )
        labels = {
            'transaction_type': 'Tipo',
            'description': 'Descrição',
            'amount': 'Valor',
            'date': 'Data',
            'account': 'Conta',
            'category': 'Categoria',
        }
        widgets = {
            # Rendered by the template as two side-by-side toggle buttons
            # (Entrada/Saída); attrs are left to the template because
            # RadioSelect also copies them to the wrapper <div>.
            'transaction_type': forms.RadioSelect,
            'description': forms.TextInput(
                attrs={
                    'class': 'input',
                    'placeholder': 'Ex.: Supermercado',
                }
            ),
            'amount': forms.NumberInput(
                attrs={
                    'class': 'input',
                    'step': '0.01',
                    'min': '0.01',
                    'placeholder': '0,00',
                }
            ),
            'date': forms.DateInput(
                attrs={'class': 'input', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'account': forms.Select(attrs={'class': 'input'}),
            'category': forms.Select(attrs={'class': 'input'}),
        }
        error_messages = {
            'transaction_type': {
                'required': 'Selecione o tipo da transação.',
            },
            'amount': {
                'min_value': 'Informe um valor maior que zero.',
            },
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # The model field has no default, so Django adds a blank choice;
        # the type selector must offer only Entrada/Saída.
        self.fields['transaction_type'].choices = (
            Transaction.TransactionType.choices
        )

        accounts = Account.objects.filter(user=user)
        active = Q(is_active=True)
        if self.instance.pk:
            # Keep the current account selectable even if deactivated.
            active |= Q(pk=self.instance.account_id)
        self.fields['account'].queryset = accounts.filter(active)
        self.fields['account'].empty_label = 'Selecione a conta'

        self.fields['category'].queryset = Category.objects.filter(
            user=user
        ).order_by('category_type', 'name')
        self.fields['category'].empty_label = 'Selecione a categoria'

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get('transaction_type')
        category = cleaned_data.get('category')
        if (
            transaction_type
            and category
            and category.category_type != transaction_type
        ):
            self.add_error(
                'category',
                'A categoria selecionada não corresponde ao tipo da '
                'transação.',
            )
        return cleaned_data


class TransactionFilterForm(forms.Form):
    start_date = forms.DateField(
        label='De',
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'input', 'type': 'date'}, format='%Y-%m-%d'
        ),
    )
    end_date = forms.DateField(
        label='Até',
        required=False,
        widget=forms.DateInput(
            attrs={'class': 'input', 'type': 'date'}, format='%Y-%m-%d'
        ),
    )
    transaction_type = forms.ChoiceField(
        label='Tipo',
        required=False,
        choices=[('', 'Todos'), *Transaction.TransactionType.choices],
        widget=forms.Select(attrs={'class': 'input'}),
    )
    account = forms.ModelChoiceField(
        label='Conta',
        required=False,
        queryset=Account.objects.none(),
        empty_label='Todas',
        widget=forms.Select(attrs={'class': 'input'}),
    )
    category = forms.ModelChoiceField(
        label='Categoria',
        required=False,
        queryset=Category.objects.none(),
        empty_label='Todas',
        widget=forms.Select(attrs={'class': 'input'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # Inactive accounts are listed too: they may hold old transactions.
        self.fields['account'].queryset = Account.objects.filter(user=user)
        self.fields['category'].queryset = Category.objects.filter(
            user=user
        ).order_by('category_type', 'name')
