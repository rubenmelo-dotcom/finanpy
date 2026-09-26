import datetime
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from core.test_utils import (
    DEFAULT_PASSWORD,
    create_account,
    create_category,
    create_transaction,
    create_user,
)
from transactions.forms import TransactionForm
from transactions.models import Transaction

INCOME = Transaction.TransactionType.INCOME
EXPENSE = Transaction.TransactionType.EXPENSE


def form_data(account, category, **extra):
    data = {
        'transaction_type': category.category_type,
        'description': 'Supermercado',
        'amount': '150.00',
        'date': '2026-03-10',
        'account': account.pk,
        'category': category.pk,
    }
    data.update(extra)
    return data


class TransactionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.transaction = create_transaction(
            cls.user, description='Mercado', amount=Decimal('42.50')
        )

    def test_str_shows_description_and_amount(self):
        self.assertEqual(str(self.transaction), 'Mercado - 42.50')

    def test_signed_amount_is_negative_for_expense(self):
        self.assertEqual(self.transaction.signed_amount, Decimal('-42.50'))

    def test_signed_amount_is_positive_for_income(self):
        category = create_category(
            self.user, name='Salário', category_type=INCOME
        )
        transaction = create_transaction(
            self.user,
            account=self.transaction.account,
            category=category,
            amount=Decimal('10.00'),
        )
        self.assertEqual(transaction.signed_amount, Decimal('10.00'))


class TransactionFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='other@example.com')
        cls.account = create_account(cls.user)
        cls.inactive_account = create_account(
            cls.user, name='Conta Antiga', is_active=False
        )
        cls.expense_category = create_category(cls.user)
        cls.income_category = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.other_account = create_account(cls.other, name='Conta Alheia')
        cls.other_category = create_category(cls.other, name='Alheia')

    def make_form(self, **extra):
        data = form_data(self.account, self.expense_category)
        data.update(extra)
        return TransactionForm(data=data, user=self.user)

    def test_valid_data_is_accepted(self):
        self.assertTrue(self.make_form().is_valid())

    def test_zero_amount_is_rejected(self):
        form = self.make_form(amount='0')
        self.assertFalse(form.is_valid())
        self.assertFormError(
            form, 'amount', 'Informe um valor maior que zero.'
        )

    def test_negative_amount_is_rejected(self):
        form = self.make_form(amount='-10.00')
        self.assertFalse(form.is_valid())
        self.assertFormError(
            form, 'amount', 'Informe um valor maior que zero.'
        )

    def test_minimum_positive_amount_is_accepted(self):
        self.assertTrue(self.make_form(amount='0.01').is_valid())

    def test_category_with_incompatible_type_is_rejected(self):
        form = self.make_form(transaction_type=INCOME)
        self.assertFalse(form.is_valid())
        self.assertFormError(
            form,
            'category',
            'A categoria selecionada não corresponde ao tipo da '
            'transação.',
        )

    def test_type_choices_have_no_blank_option(self):
        form = TransactionForm(user=self.user)
        self.assertEqual(
            list(form.fields['transaction_type'].choices),
            list(Transaction.TransactionType.choices),
        )

    def test_account_select_lists_only_active_accounts_of_user(self):
        form = TransactionForm(user=self.user)
        self.assertQuerySetEqual(
            form.fields['account'].queryset,
            [self.account],
            ordered=False,
        )

    def test_category_select_lists_only_categories_of_user(self):
        form = TransactionForm(user=self.user)
        self.assertQuerySetEqual(
            form.fields['category'].queryset,
            [self.expense_category, self.income_category],
            ordered=False,
        )

    def test_account_of_other_user_is_rejected(self):
        form = self.make_form(account=self.other_account.pk)
        self.assertFalse(form.is_valid())
        self.assertIn('account', form.errors)

    def test_category_of_other_user_is_rejected(self):
        form = self.make_form(category=self.other_category.pk)
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_inactive_account_is_rejected_on_create(self):
        form = self.make_form(account=self.inactive_account.pk)
        self.assertFalse(form.is_valid())
        self.assertIn('account', form.errors)

    def test_edit_keeps_current_inactive_account_selectable(self):
        transaction = create_transaction(
            self.user,
            account=self.inactive_account,
            category=self.expense_category,
        )
        form = TransactionForm(instance=transaction, user=self.user)
        self.assertQuerySetEqual(
            form.fields['account'].queryset,
            [self.account, self.inactive_account],
            ordered=False,
        )


class TransactionListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='other@example.com')
        cls.checking = create_account(cls.user)
        cls.savings = create_account(
            cls.user, name='Poupança', is_active=False
        )
        cls.food = create_category(cls.user)
        cls.transport = create_category(cls.user, name='Transporte')
        cls.salary = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.salary_jan = create_transaction(
            cls.user,
            account=cls.checking,
            category=cls.salary,
            description='Salário janeiro',
            amount=Decimal('5000.00'),
            date=datetime.date(2026, 1, 5),
        )
        cls.market_jan = create_transaction(
            cls.user,
            account=cls.checking,
            category=cls.food,
            description='Mercado janeiro',
            amount=Decimal('300.00'),
            date=datetime.date(2026, 1, 20),
        )
        cls.bus_feb = create_transaction(
            cls.user,
            account=cls.savings,
            category=cls.transport,
            description='Ônibus fevereiro',
            amount=Decimal('50.00'),
            date=datetime.date(2026, 2, 10),
        )
        cls.bonus_mar = create_transaction(
            cls.user,
            account=cls.savings,
            category=cls.salary,
            description='Bônus março',
            amount=Decimal('800.00'),
            date=datetime.date(2026, 3, 1),
        )
        cls.other_transaction = create_transaction(
            cls.other, description='Alheia', amount=Decimal('999.00')
        )
        cls.url = reverse('transactions:list')

    def setUp(self):
        self.client.force_login(self.user)

    def get_list(self, **params):
        return self.client.get(self.url, params)

    def assert_listed(self, response, expected):
        self.assertQuerySetEqual(
            response.context['object_list'], expected, ordered=False
        )

    def test_list_requires_login(self):
        self.client.logout()
        response = self.get_list()
        self.assertRedirects(
            response, f'{reverse("login")}?next={self.url}'
        )

    def test_list_shows_only_transactions_of_user(self):
        response = self.get_list()
        self.assertEqual(response.status_code, 200)
        self.assert_listed(
            response,
            [self.salary_jan, self.market_jan, self.bus_feb,
             self.bonus_mar],
        )
        self.assertNotContains(response, 'Alheia')
        self.assertFalse(response.context['is_filtered'])

    def test_list_is_ordered_by_most_recent_date(self):
        response = self.get_list()
        self.assertEqual(
            list(response.context['object_list']),
            [self.bonus_mar, self.bus_feb, self.market_jan,
             self.salary_jan],
        )

    def test_filter_by_period(self):
        response = self.get_list(
            start_date='2026-01-15', end_date='2026-02-28'
        )
        self.assert_listed(response, [self.market_jan, self.bus_feb])
        self.assertTrue(response.context['is_filtered'])

    def test_filter_by_start_date_only(self):
        response = self.get_list(start_date='2026-02-10')
        self.assert_listed(response, [self.bus_feb, self.bonus_mar])

    def test_filter_by_end_date_only(self):
        response = self.get_list(end_date='2026-01-20')
        self.assert_listed(response, [self.salary_jan, self.market_jan])

    def test_filter_by_type(self):
        response = self.get_list(transaction_type=INCOME)
        self.assert_listed(response, [self.salary_jan, self.bonus_mar])

    def test_filter_by_account_includes_inactive_account(self):
        response = self.get_list(account=self.savings.pk)
        self.assert_listed(response, [self.bus_feb, self.bonus_mar])

    def test_filter_by_category(self):
        response = self.get_list(category=self.food.pk)
        self.assert_listed(response, [self.market_jan])

    def test_combined_filters(self):
        response = self.get_list(
            transaction_type=INCOME,
            account=self.checking.pk,
            end_date='2026-12-31',
        )
        self.assert_listed(response, [self.salary_jan])

    def test_filter_without_matches_returns_empty_list(self):
        response = self.get_list(start_date='2027-01-01')
        self.assert_listed(response, [])
        self.assertTrue(response.context['has_transactions'])

    def test_invalid_filters_are_ignored(self):
        response = self.get_list(
            start_date='data-invalida', transaction_type='xyz'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['object_list'].count(), 4)
        self.assertFalse(response.context['is_filtered'])

    def test_filter_by_account_of_other_user_is_ignored(self):
        response = self.get_list(
            account=self.other_transaction.account.pk
        )
        self.assertEqual(response.context['object_list'].count(), 4)
        self.assertNotContains(response, 'Alheia')

    def test_totals_without_filters(self):
        response = self.get_list()
        self.assertEqual(
            response.context['total_income'], Decimal('5800.00')
        )
        self.assertEqual(
            response.context['total_expense'], Decimal('350.00')
        )
        self.assertEqual(response.context['balance'], Decimal('5450.00'))

    def test_totals_match_filtered_records(self):
        response = self.get_list(
            start_date='2026-01-01', end_date='2026-01-31'
        )
        self.assertEqual(
            response.context['total_income'], Decimal('5000.00')
        )
        self.assertEqual(
            response.context['total_expense'], Decimal('300.00')
        )
        self.assertEqual(response.context['balance'], Decimal('4700.00'))

    def test_totals_are_zero_when_filter_has_no_income(self):
        response = self.get_list(account=self.checking.pk,
                                 transaction_type=EXPENSE)
        self.assertEqual(response.context['total_income'], Decimal('0'))
        self.assertEqual(
            response.context['total_expense'], Decimal('300.00')
        )
        self.assertEqual(response.context['balance'], Decimal('-300.00'))

    def test_totals_consider_all_pages(self):
        for day in range(1, 22):
            create_transaction(
                self.user,
                account=self.checking,
                category=self.food,
                amount=Decimal('10.00'),
                date=datetime.date(2025, 12, day),
            )
        response = self.get_list(
            start_date='2025-12-01', end_date='2025-12-31'
        )
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['transactions']), 20)
        self.assertEqual(
            response.context['total_expense'], Decimal('210.00')
        )

    def test_empty_list_for_new_user(self):
        create_user(email='new@example.com')
        self.client.login(email='new@example.com',
                          password=DEFAULT_PASSWORD)
        response = self.get_list()
        self.assertFalse(response.context['has_transactions'])
        self.assertEqual(response.context['balance'], Decimal('0'))


class TransactionCrudViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='other@example.com')
        cls.account = create_account(cls.user)
        cls.category = create_category(cls.user)
        cls.income_category = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.other_transaction = create_transaction(
            cls.other, description='Alheia'
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.transaction = create_transaction(
            self.user,
            account=self.account,
            category=self.category,
            description='Farmácia',
            date=datetime.date(2026, 2, 1),
        )

    def messages_of(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_create_page_renders(self):
        response = self.client.get(reverse('transactions:create'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_accounts'])
        self.assertTrue(response.context['has_categories'])

    def test_create_page_preselects_type_from_query_string(self):
        response = self.client.get(
            reverse('transactions:create'), {'tipo': INCOME}
        )
        self.assertEqual(
            response.context['form'].initial['transaction_type'], INCOME
        )

    def test_create_page_ignores_invalid_type_in_query_string(self):
        response = self.client.get(
            reverse('transactions:create'), {'tipo': 'xyz'}
        )
        self.assertNotIn(
            'transaction_type', response.context['form'].initial
        )

    def test_create_page_flags_missing_accounts_and_categories(self):
        create_user(email='new@example.com')
        self.client.login(email='new@example.com',
                          password=DEFAULT_PASSWORD)
        response = self.client.get(reverse('transactions:create'))
        self.assertFalse(response.context['has_accounts'])
        self.assertFalse(response.context['has_categories'])

    def test_create_assigns_logged_user(self):
        response = self.client.post(
            reverse('transactions:create'),
            form_data(self.account, self.income_category,
                      description='Salário março', amount='3000.00'),
        )
        self.assertRedirects(response, reverse('transactions:list'))
        transaction = Transaction.objects.get(description='Salário março')
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.amount, Decimal('3000.00'))
        self.assertEqual(transaction.transaction_type, INCOME)
        self.assertIn(
            'Transação registrada com sucesso.',
            self.messages_of(response),
        )

    def test_create_with_zero_amount_does_not_save(self):
        response = self.client.post(
            reverse('transactions:create'),
            form_data(self.account, self.category, amount='0'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'amount',
            'Informe um valor maior que zero.',
        )
        self.assertEqual(
            Transaction.objects.filter(user=self.user).count(), 1
        )

    def test_create_with_incompatible_category_does_not_save(self):
        response = self.client.post(
            reverse('transactions:create'),
            form_data(self.account, self.category,
                      transaction_type=INCOME),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'A categoria selecionada não corresponde'
        )
        self.assertEqual(
            Transaction.objects.filter(user=self.user).count(), 1
        )

    def test_create_requires_login(self):
        self.client.logout()
        url = reverse('transactions:create')
        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("login")}?next={url}')

    def test_update_changes_transaction(self):
        url = reverse('transactions:update', args=[self.transaction.pk])
        response = self.client.post(
            url,
            form_data(self.account, self.category,
                      description='Farmácia editada', amount='75.30'),
        )
        self.assertRedirects(response, reverse('transactions:list'))
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.description, 'Farmácia editada')
        self.assertEqual(self.transaction.amount, Decimal('75.30'))
        self.assertEqual(self.transaction.user, self.user)
        self.assertIn(
            'Transação atualizada com sucesso.',
            self.messages_of(response),
        )

    def test_update_page_renders_for_owner(self):
        response = self.client.get(
            reverse('transactions:update', args=[self.transaction.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Farmácia')

    def test_delete_confirmation_page_renders(self):
        response = self.client.get(
            reverse('transactions:delete', args=[self.transaction.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_removes_transaction(self):
        response = self.client.post(
            reverse('transactions:delete', args=[self.transaction.pk])
        )
        self.assertRedirects(response, reverse('transactions:list'))
        self.assertFalse(
            Transaction.objects.filter(pk=self.transaction.pk).exists()
        )
        self.assertIn(
            'Transação excluída com sucesso.',
            self.messages_of(response),
        )

    def test_update_of_other_user_returns_404(self):
        url = reverse(
            'transactions:update', args=[self.other_transaction.pk]
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        response = self.client.post(
            url,
            form_data(self.account, self.category, description='Hack'),
        )
        self.assertEqual(response.status_code, 404)
        self.other_transaction.refresh_from_db()
        self.assertEqual(self.other_transaction.description, 'Alheia')

    def test_delete_of_other_user_returns_404(self):
        url = reverse(
            'transactions:delete', args=[self.other_transaction.pk]
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(
            Transaction.objects.filter(
                pk=self.other_transaction.pk
            ).exists()
        )

    def test_update_and_delete_require_login(self):
        self.client.logout()
        for name in ('transactions:update', 'transactions:delete'):
            url = reverse(name, args=[self.transaction.pk])
            response = self.client.get(url)
            self.assertRedirects(
                response, f'{reverse("login")}?next={url}'
            )

    def test_category_type_choices_match_transaction_types(self):
        self.assertEqual(
            set(Category.CategoryType.values),
            set(Transaction.TransactionType.values),
        )
