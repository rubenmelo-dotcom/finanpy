from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from categories.models import Category
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)
from transactions.models import Transaction


def message_texts(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class AccountBalanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.account = create_account(
            cls.user, initial_balance=Decimal('1000.00')
        )

    def test_str_returns_name(self):
        self.assertEqual(str(self.account), 'Conta Principal')

    def test_current_balance_without_transactions_is_initial_balance(self):
        self.assertEqual(
            self.account.current_balance(), Decimal('1000.00')
        )

    def test_current_balance_considers_income_and_expense(self):
        income = create_category(
            self.user,
            name='Salário',
            category_type=Category.CategoryType.INCOME,
        )
        expense = create_category(self.user, name='Mercado')
        create_transaction(
            self.user, self.account, income, amount=Decimal('500.50')
        )
        create_transaction(
            self.user, self.account, expense, amount=Decimal('200.25')
        )
        create_transaction(
            self.user, self.account, expense, amount=Decimal('100.00')
        )

        self.assertEqual(
            self.account.current_balance(), Decimal('1200.25')
        )

    def test_current_balance_ignores_other_accounts(self):
        other = create_account(self.user, name='Poupança')
        create_transaction(self.user, account=other)

        self.assertEqual(
            self.account.current_balance(), Decimal('1000.00')
        )

    def test_with_balance_annotation_matches_current_balance(self):
        create_transaction(
            self.user,
            self.account,
            transaction_type=Transaction.TransactionType.EXPENSE,
            amount=Decimal('50.00'),
        )
        annotated = Account.objects.with_balance(self.user).get(
            pk=self.account.pk
        )

        self.assertEqual(annotated.balance, Decimal('950.00'))
        self.assertEqual(
            annotated.balance, self.account.current_balance()
        )


class AccountViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other_user = create_user(email='other@example.com')
        cls.account = create_account(cls.user, name='Minha Conta')
        cls.other_account = create_account(
            cls.other_user, name='Conta Alheia'
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_list_requires_login(self):
        self.client.logout()
        url = reverse('accounts:list')

        response = self.client.get(url)

        self.assertRedirects(response, f'{reverse("login")}?next={url}')

    def test_list_shows_only_logged_user_accounts(self):
        response = self.client.get(reverse('accounts:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Minha Conta')
        self.assertNotContains(response, 'Conta Alheia')
        self.assertEqual(
            list(response.context['accounts']), [self.account]
        )

    def test_list_shows_empty_state_without_accounts(self):
        self.client.force_login(create_user(email='new@example.com'))

        response = self.client.get(reverse('accounts:list'))

        self.assertContains(response, 'Nenhuma conta cadastrada')

    def test_create_assigns_logged_user(self):
        response = self.client.post(
            reverse('accounts:create'),
            {
                'name': 'Carteira',
                'bank_name': '',
                'account_type': Account.AccountType.WALLET,
                'initial_balance': '150.75',
                'is_active': 'on',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('accounts:list'))
        account = Account.objects.get(name='Carteira')
        self.assertEqual(account.user, self.user)
        self.assertEqual(account.initial_balance, Decimal('150.75'))
        self.assertContains(response, 'Conta criada com sucesso.')

    def test_create_with_invalid_data_shows_errors(self):
        response = self.client.post(
            reverse('accounts:create'),
            {'name': '', 'account_type': 'invalid'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], 'name', 'Este campo é obrigatório.'
        )
        self.assertFalse(Account.objects.filter(name='').exists())

    def test_update_own_account(self):
        response = self.client.post(
            reverse('accounts:update', args=[self.account.pk]),
            {
                'name': 'Conta Editada',
                'bank_name': 'Banco Novo',
                'account_type': Account.AccountType.SAVINGS,
                'initial_balance': '10.00',
            },
        )

        self.assertRedirects(response, reverse('accounts:list'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, 'Conta Editada')
        self.assertFalse(self.account.is_active)
        self.assertIn('Conta atualizada com sucesso.', message_texts(response))

    def test_update_other_user_account_returns_404(self):
        url = reverse('accounts:update', args=[self.other_account.pk])

        self.assertEqual(self.client.get(url).status_code, 404)
        response = self.client.post(url, {'name': 'Hack'})
        self.assertEqual(response.status_code, 404)
        self.other_account.refresh_from_db()
        self.assertEqual(self.other_account.name, 'Conta Alheia')

    def test_delete_other_user_account_returns_404(self):
        url = reverse('accounts:delete', args=[self.other_account.pk])

        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(
            Account.objects.filter(pk=self.other_account.pk).exists()
        )

    def test_delete_own_account_without_transactions(self):
        url = reverse('accounts:delete', args=[self.account.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(url)

        self.assertRedirects(response, reverse('accounts:list'))
        self.assertFalse(
            Account.objects.filter(pk=self.account.pk).exists()
        )
        self.assertIn('Conta excluída com sucesso.', message_texts(response))

    def test_delete_account_with_transactions_is_blocked(self):
        create_transaction(self.user, account=self.account)

        response = self.client.post(
            reverse('accounts:delete', args=[self.account.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('accounts:list'))
        self.assertTrue(
            Account.objects.filter(pk=self.account.pk).exists()
        )
        self.assertContains(
            response,
            'Esta conta possui transações e não pode ser excluída. '
            'Você pode desativá-la.',
        )
