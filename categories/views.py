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

from accounts.views import UserQuerySetMixin
from categories.forms import CategoryForm
from categories.models import Category


class CategoryFormKwargsMixin:
    """Pass the logged user to CategoryForm (duplicate validation)."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class CategoryListView(LoginRequiredMixin, UserQuerySetMixin, ListView):
    model = Category
    context_object_name = 'categories'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = list(context['categories'])
        context['income_categories'] = [
            category for category in categories
            if category.category_type == Category.CategoryType.INCOME
        ]
        context['expense_categories'] = [
            category for category in categories
            if category.category_type == Category.CategoryType.EXPENSE
        ]
        return context


class CategoryCreateView(
    LoginRequiredMixin,
    CategoryFormKwargsMixin,
    SuccessMessageMixin,
    CreateView,
):
    model = Category
    form_class = CategoryForm
    success_url = reverse_lazy('categories:list')
    success_message = 'Categoria criada com sucesso.'

    def get_initial(self):
        initial = super().get_initial()
        category_type = self.request.GET.get('tipo')
        if category_type in Category.CategoryType.values:
            initial['category_type'] = category_type
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class CategoryUpdateView(
    LoginRequiredMixin,
    UserQuerySetMixin,
    CategoryFormKwargsMixin,
    SuccessMessageMixin,
    UpdateView,
):
    model = Category
    form_class = CategoryForm
    success_url = reverse_lazy('categories:list')
    success_message = 'Categoria atualizada com sucesso.'


class CategoryDeleteView(
    LoginRequiredMixin, UserQuerySetMixin, DeleteView
):
    model = Category
    success_url = reverse_lazy('categories:list')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'Esta categoria possui transações e não pode ser '
                'excluída.',
            )
            return redirect(self.success_url)
        messages.success(self.request, 'Categoria excluída com sucesso.')
        return response
