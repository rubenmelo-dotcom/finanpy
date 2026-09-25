from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
)

from accounts.models import Account
from accounts.views import UserQuerySetMixin
from categories.models import Category
from transactions.forms import TransactionFilterForm, TransactionForm
from transactions.models import Transaction

MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO = Value(Decimal('0'), output_field=MONEY)


def _sum_by_type(transaction_type):
    return Coalesce(
        Sum('amount', filter=Q(transaction_type=transaction_type)),
        ZERO,
        output_field=MONEY,
    )


class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    context_object_name = 'transactions'
    paginate_by = 20

    # Maps each filter field to the queryset lookup it applies.
    filter_lookups = {
        'start_date': 'date__gte',
        'end_date': 'date__lte',
        'transaction_type': 'transaction_type',
        'account': 'account',
        'category': 'category',
    }

    def get_queryset(self):
        queryset = Transaction.objects.filter(
            user=self.request.user
        ).select_related('account', 'category')
        self.filter_form = TransactionFilterForm(
            self.request.GET, user=self.request.user
        )
        self.is_filtered = False
        if self.filter_form.is_valid():
            filters = {
                lookup: self.filter_form.cleaned_data[field]
                for field, lookup in self.filter_lookups.items()
                if self.filter_form.cleaned_data.get(field)
            }
            self.is_filtered = bool(filters)
            queryset = queryset.filter(**filters)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # object_list is the filtered queryset before pagination.
        totals = self.object_list.aggregate(
            total_income=_sum_by_type(Transaction.TransactionType.INCOME),
            total_expense=_sum_by_type(
                Transaction.TransactionType.EXPENSE
            ),
        )
        context.update(totals)
        context['balance'] = (
            totals['total_income'] - totals['total_expense']
        )
        context['filter_form'] = self.filter_form
        context['is_filtered'] = self.is_filtered
        if self.is_filtered:
            context['has_transactions'] = Transaction.objects.filter(
                user=self.request.user
            ).exists()
        else:
            context['has_transactions'] = bool(context['transactions'])
        return context


class TransactionFormMixin:
    """Shared setup for the create/update views (form user and hints)."""

    model = Transaction
    form_class = TransactionForm
    success_url = reverse_lazy('transactions:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['has_accounts'] = Account.objects.filter(
            user=user, is_active=True
        ).exists()
        context['has_categories'] = Category.objects.filter(
            user=user
        ).exists()
        return context


class TransactionCreateView(
    LoginRequiredMixin,
    TransactionFormMixin,
    SuccessMessageMixin,
    CreateView,
):
    success_message = 'Transação registrada com sucesso.'

    def get_initial(self):
        initial = super().get_initial()
        transaction_type = self.request.GET.get('tipo')
        if transaction_type in Transaction.TransactionType.values:
            initial['transaction_type'] = transaction_type
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TransactionUpdateView(
    LoginRequiredMixin,
    UserQuerySetMixin,
    TransactionFormMixin,
    SuccessMessageMixin,
    UpdateView,
):
    success_message = 'Transação atualizada com sucesso.'


class TransactionDeleteView(
    LoginRequiredMixin,
    UserQuerySetMixin,
    SuccessMessageMixin,
    DeleteView,
):
    model = Transaction
    success_url = reverse_lazy('transactions:list')
    success_message = 'Transação excluída com sucesso.'
