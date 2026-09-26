from datetime import timedelta
from decimal import Decimal

from django import forms
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from core.forms import INVALID_EMAIL_MESSAGE, StyledFormMixin
from core.templatetags.currency import currency
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)

INCOME = Category.CategoryType.INCOME
EXPENSE = Category.CategoryType.EXPENSE


def previous_month_date():
    """Last day of the previous month, relative to today."""
    return timezone.localdate().replace(day=1) - timedelta(days=1)


class HomeViewTests(TestCase):
    def test_home_returns_200_for_anonymous_user(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, 'Cadastre-se')

    def test_home_shows_dashboard_link_for_authenticated_user(self):
        self.client.force_login(create_user())

        response = self.client.get(reverse('home'))

        self.assertContains(response, 'Ir para o dashboard')


class DashboardAccessTests(TestCase):
    def test_dashboard_redirects_anonymous_user_to_login(self):
        url = reverse('dashboard')

        response = self.client.get(url)

        self.assertRedirects(
            response, f'{reverse("login")}?next={url}'
        )

    def test_dashboard_returns_200_for_authenticated_user(self):
        self.client.force_login(create_user())

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')

    def test_empty_dashboard_has_zero_totals_and_onboarding(self):
        self.client.force_login(create_user())

        response = self.client.get(reverse('dashboard'))

        context = response.context
        self.assertEqual(context['total_balance'], Decimal('0.00'))
        self.assertEqual(context['month_income'], Decimal('0.00'))
        self.assertEqual(context['month_expense'], Decimal('0.00'))
        self.assertEqual(context['expenses_by_category'], [])
        self.assertFalse(context['onboarding_complete'])
        self.assertContains(response, 'Primeiros passos')


class DashboardTotalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.account = create_account(
            cls.user, initial_balance=Decimal('0.00')
        )
        cls.income_category = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.food = create_category(cls.user, name='Alimentação')
        cls.transport = create_category(cls.user, name='Transporte')
        today = timezone.localdate()
        last_month = previous_month_date()

        create_transaction(
            cls.user, cls.account, cls.income_category,
            amount=Decimal('5000.00'), date=today,
        )
        create_transaction(
            cls.user, cls.account, cls.food,
            amount=Decimal('300.00'), date=today,
        )
        create_transaction(
            cls.user, cls.account, cls.transport,
            amount=Decimal('100.00'), date=today,
        )
        # Previous month: must be ignored by the month totals.
        create_transaction(
            cls.user, cls.account, cls.income_category,
            amount=Decimal('999.00'), date=last_month,
        )
        create_transaction(
            cls.user, cls.account, cls.food,
            amount=Decimal('777.00'), date=last_month,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def get_context(self):
        return self.client.get(reverse('dashboard')).context

    def test_month_totals_ignore_previous_month_transactions(self):
        context = self.get_context()

        self.assertEqual(context['month_income'], Decimal('5000.00'))
        self.assertEqual(context['month_expense'], Decimal('400.00'))
        self.assertEqual(context['month_result'], Decimal('4600.00'))

    def test_month_totals_ignore_other_users_transactions(self):
        other = create_user(email='other@example.com')
        create_transaction(
            other, amount=Decimal('50.00'), description='Outro'
        )

        context = self.get_context()

        self.assertEqual(context['month_expense'], Decimal('400.00'))

    def test_expenses_by_category_totals_and_percentages(self):
        context = self.get_context()

        self.assertEqual(
            context['expenses_by_category'],
            [
                {
                    'name': 'Alimentação',
                    'color': self.food.color,
                    'total': Decimal('300.00'),
                    'percent': 75,
                },
                {
                    'name': 'Transporte',
                    'color': self.transport.color,
                    'total': Decimal('100.00'),
                    'percent': 25,
                },
            ],
        )

    def test_expenses_by_category_ignore_income_and_previous_month(self):
        context = self.get_context()

        names = [item['name'] for item in context['expenses_by_category']]
        self.assertNotIn('Salário', names)
        self.assertEqual(
            context['expenses_by_category'][0]['total'], Decimal('300.00')
        )

    def test_onboarding_complete_when_user_has_all_data(self):
        response = self.client.get(reverse('dashboard'))

        self.assertTrue(response.context['onboarding_complete'])
        self.assertNotContains(response, 'Primeiros passos')

    def test_recent_transactions_limited_to_five(self):
        for index in range(4):
            create_transaction(
                self.user, self.account, self.food,
                description=f'Extra {index}',
            )

        context = self.get_context()

        self.assertEqual(len(context['recent_transactions']), 5)


class DashboardBalanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.active = create_account(
            cls.user, name='Ativa', initial_balance=Decimal('1000.00')
        )
        cls.inactive = create_account(
            cls.user,
            name='Inativa',
            initial_balance=Decimal('500.00'),
            is_active=False,
        )
        cls.income = create_category(
            cls.user, name='Salário', category_type=INCOME
        )
        cls.expense = create_category(cls.user)
        create_transaction(
            cls.user, cls.active, cls.income, amount=Decimal('200.00')
        )
        create_transaction(
            cls.user, cls.active, cls.expense, amount=Decimal('50.00'),
            date=previous_month_date(),
        )
        create_transaction(
            cls.user, cls.inactive, cls.income, amount=Decimal('300.00')
        )
        other = create_user(email='other@example.com')
        create_account(other, initial_balance=Decimal('9000.00'))

    def setUp(self):
        self.client.force_login(self.user)

    def test_total_balance_sums_only_active_accounts(self):
        response = self.client.get(reverse('dashboard'))

        # 1000 + 200 - 50 (all periods); inactive account is ignored.
        self.assertEqual(
            response.context['total_balance'], Decimal('1150.00')
        )

    def test_accounts_list_contains_only_active_accounts(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.context['accounts'], [self.active])


class CurrencyFilterTests(TestCase):
    def test_formats_positive_value(self):
        self.assertEqual(currency(Decimal('1234.5')), 'R$ 1.234,50')

    def test_formats_negative_value_with_sign_before_symbol(self):
        self.assertEqual(currency(Decimal('-10')), '−R$ 10,00')

    def test_returns_empty_string_for_empty_values(self):
        self.assertEqual(currency(None), '')
        self.assertEqual(currency(''), '')

    def test_filter_is_available_in_templates(self):
        rendered = Template(
            '{% load currency %}{{ value|currency }}'
        ).render(Context({'value': Decimal('5')}))

        self.assertEqual(rendered, 'R$ 5,00')


class StyledFormMixinTests(TestCase):
    class SampleForm(StyledFormMixin, forms.Form):
        email = forms.EmailField(
            widget=forms.EmailInput(attrs={'class': 'input'})
        )
        choice = forms.ChoiceField(
            choices=[('a', 'A')], widget=forms.RadioSelect
        )

    def test_invalid_field_gets_error_class_and_aria_invalid(self):
        form = self.SampleForm(data={'email': 'invalido', 'choice': 'a'})

        self.assertFalse(form.is_valid())
        attrs = form.fields['email'].widget.attrs
        self.assertIn('input-error', attrs['class'].split())
        self.assertEqual(attrs['aria-invalid'], 'true')

    def test_email_error_message_is_in_portuguese(self):
        form = self.SampleForm(data={'email': 'invalido', 'choice': 'a'})

        self.assertFormError(form, 'email', INVALID_EMAIL_MESSAGE)

    def test_radio_select_widget_is_not_marked(self):
        form = self.SampleForm(data={'email': 'a@example.com'})

        self.assertFalse(form.is_valid())
        self.assertNotIn(
            'aria-invalid', form.fields['choice'].widget.attrs
        )
