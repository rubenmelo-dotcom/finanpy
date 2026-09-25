from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
)

from accounts.forms import AccountForm
from accounts.models import Account


class UserQuerySetMixin:
    """Limit the queryset to the logged user (other pk -> 404)."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class AccountListView(LoginRequiredMixin, ListView):
    model = Account
    context_object_name = 'accounts'

    def get_queryset(self):
        return Account.objects.with_balance(self.request.user)


class AccountCreateView(
    LoginRequiredMixin, SuccessMessageMixin, CreateView
):
    model = Account
    form_class = AccountForm
    success_url = reverse_lazy('accounts:list')
    success_message = 'Conta criada com sucesso.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class AccountUpdateView(
    LoginRequiredMixin, UserQuerySetMixin, SuccessMessageMixin, UpdateView
):
    model = Account
    form_class = AccountForm
    success_url = reverse_lazy('accounts:list')
    success_message = 'Conta atualizada com sucesso.'


class AccountDeleteView(LoginRequiredMixin, UserQuerySetMixin, DeleteView):
    model = Account
    success_url = reverse_lazy('accounts:list')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'Esta conta possui transações e não pode ser excluída. '
                'Você pode desativá-la.',
            )
            return redirect(self.success_url)
        messages.success(self.request, 'Conta excluída com sucesso.')
        return response
