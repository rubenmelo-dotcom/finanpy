from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from categories.forms import CategoryForm
from categories.models import Category
from core.test_utils import (
    create_category,
    create_transaction,
    create_user,
)

INCOME = Category.CategoryType.INCOME
EXPENSE = Category.CategoryType.EXPENSE
DUPLICATE_ERROR = 'Já existe uma categoria com este nome para este tipo.'


def message_texts(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class CategoryFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.category = create_category(
            cls.user, name='Alimentação', category_type=EXPENSE
        )

    def build_form(self, name, category_type, user=None, **kwargs):
        data = {
            'name': name,
            'category_type': category_type,
            'color': '#10B981',
        }
        return CategoryForm(data=data, user=user or self.user, **kwargs)

    def test_str_returns_name(self):
        self.assertEqual(str(self.category), 'Alimentação')

    def test_duplicate_name_and_type_is_rejected(self):
        form = self.build_form('Alimentação', EXPENSE)

        self.assertFalse(form.is_valid())
        self.assertFormError(form, None, DUPLICATE_ERROR)

    def test_duplicate_check_ignores_case_and_spaces(self):
        form = self.build_form('  ALIMENTAÇÃO ', EXPENSE)

        self.assertFalse(form.is_valid())
        self.assertFormError(form, None, DUPLICATE_ERROR)

    def test_same_name_with_different_type_is_allowed(self):
        form = self.build_form('Alimentação', INCOME)

        self.assertTrue(form.is_valid(), form.errors)
        category = form.save(commit=False)
        category.user = self.user
        category.save()
        self.assertEqual(
            Category.objects.filter(
                user=self.user, name='Alimentação'
            ).count(),
            2,
        )

    def test_same_name_for_other_user_is_allowed(self):
        other_user = create_user(email='other@example.com')

        form = self.build_form('Alimentação', EXPENSE, user=other_user)

        self.assertTrue(form.is_valid(), form.errors)

    def test_update_keeping_same_name_is_allowed(self):
        form = self.build_form(
            'Alimentação', EXPENSE, instance=self.category
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_color_is_rejected(self):
        form = CategoryForm(
            data={
                'name': 'Lazer',
                'category_type': EXPENSE,
                'color': '#000000',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertFormError(form, 'color', 'Selecione uma cor válida.')


class CategoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other_user = create_user(email='other@example.com')
        cls.category = create_category(
            cls.user, name='Mercado', category_type=EXPENSE
        )
        cls.income = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.other_category = create_category(
            cls.other_user, name='Categoria Alheia'
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_list_requires_login(self):
        self.client.logout()
        url = reverse('categories:list')

        response = self.client.get(url)

        self.assertRedirects(response, f'{reverse("login")}?next={url}')

    def test_list_shows_only_logged_user_categories_grouped(self):
        response = self.client.get(reverse('categories:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mercado')
        self.assertContains(response, 'Salário')
        self.assertNotContains(response, 'Categoria Alheia')
        self.assertEqual(
            response.context['expense_categories'], [self.category]
        )
        self.assertEqual(
            response.context['income_categories'], [self.income]
        )

    def test_create_uses_type_from_query_string(self):
        response = self.client.get(
            reverse('categories:create'), {'tipo': INCOME}
        )

        self.assertEqual(
            response.context['form'].initial['category_type'], INCOME
        )

    def test_create_ignores_invalid_type_in_query_string(self):
        response = self.client.get(
            reverse('categories:create'), {'tipo': 'invalid'}
        )

        self.assertNotIn(
            'category_type', response.context['form'].initial
        )

    def test_create_assigns_logged_user(self):
        response = self.client.post(
            reverse('categories:create'),
            {
                'name': 'Transporte',
                'category_type': EXPENSE,
                'color': '#22D3EE',
            },
        )

        self.assertRedirects(response, reverse('categories:list'))
        category = Category.objects.get(name='Transporte')
        self.assertEqual(category.user, self.user)
        self.assertEqual(category.color, '#22D3EE')
        self.assertIn(
            'Categoria criada com sucesso.', message_texts(response)
        )

    def test_create_duplicate_through_view_shows_error(self):
        response = self.client.post(
            reverse('categories:create'),
            {'name': 'Mercado', 'category_type': EXPENSE,
             'color': '#22D3EE'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], None, DUPLICATE_ERROR)
        self.assertEqual(
            Category.objects.filter(user=self.user, name='Mercado').count(),
            1,
        )

    def test_create_same_name_with_other_type_through_view(self):
        response = self.client.post(
            reverse('categories:create'),
            {'name': 'Mercado', 'category_type': INCOME,
             'color': '#22D3EE'},
        )

        self.assertRedirects(response, reverse('categories:list'))
        self.assertEqual(
            Category.objects.filter(user=self.user, name='Mercado').count(),
            2,
        )

    def test_update_own_category(self):
        response = self.client.post(
            reverse('categories:update', args=[self.category.pk]),
            {'name': 'Supermercado', 'category_type': EXPENSE,
             'color': '#F43F5E'},
        )

        self.assertRedirects(response, reverse('categories:list'))
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'Supermercado')
        self.assertIn(
            'Categoria atualizada com sucesso.', message_texts(response)
        )

    def test_update_other_user_category_returns_404(self):
        url = reverse('categories:update', args=[self.other_category.pk])

        self.assertEqual(self.client.get(url).status_code, 404)
        response = self.client.post(
            url,
            {'name': 'Hack', 'category_type': EXPENSE, 'color': '#22D3EE'},
        )
        self.assertEqual(response.status_code, 404)
        self.other_category.refresh_from_db()
        self.assertEqual(self.other_category.name, 'Categoria Alheia')

    def test_delete_other_user_category_returns_404(self):
        url = reverse('categories:delete', args=[self.other_category.pk])

        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(
            Category.objects.filter(pk=self.other_category.pk).exists()
        )

    def test_delete_own_category_without_transactions(self):
        url = reverse('categories:delete', args=[self.category.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(url)

        self.assertRedirects(response, reverse('categories:list'))
        self.assertFalse(
            Category.objects.filter(pk=self.category.pk).exists()
        )
        self.assertIn(
            'Categoria excluída com sucesso.', message_texts(response)
        )

    def test_delete_category_with_transactions_is_blocked(self):
        create_transaction(self.user, category=self.category)

        response = self.client.post(
            reverse('categories:delete', args=[self.category.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('categories:list'))
        self.assertTrue(
            Category.objects.filter(pk=self.category.pk).exists()
        )
        self.assertContains(
            response,
            'Esta categoria possui transações e não pode ser excluída.',
        )
