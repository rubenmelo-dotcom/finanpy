import json
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.test import TestCase
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime

from ai.agent import build_agent
from ai.tests.utils import (
    fake_model,
    make_context,
    structured_response_message,
    tool_call_message,
)
from ai.tools import (
    ANALYSIS_TOOLS,
    ReadOnlyQueryError,
    get_account_balances,
    get_categories,
    get_category_breakdown,
    get_financial_overview,
    get_largest_transactions,
    read_only_queries,
    share_connection_with_tools,
)
from categories.models import Category
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)
from transactions.models import Transaction

PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 9, 20)
INCOME = Category.CategoryType.INCOME


def runtime_for(context):
    """``ToolRuntime`` for calling a tool outside the agent."""
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda chunk: None,
        tool_call_id='test-call',
        store=None,
    )


def seed_user(user, scale=1):
    """Create accounts, categories and transactions for ``user``.

    Totals (``scale=1``):
    - 2026-08: income 3000.00; expense 1000.00 (Alimentação 700, Lazer 300)
    - 2026-09: income 3000.00; expense 2000.00 (Alimentação 1500,
      Lazer 500)
    - 2026-05 (outside the period): expense 999.00
    """
    main = create_account(
        user, name='Conta Principal', initial_balance=Decimal('1000.00'),
    )
    savings = create_account(
        user, name='Poupança', account_type='savings',
        initial_balance=Decimal('500.00'),
    )
    create_account(
        user, name='Antiga', initial_balance=Decimal('9999.00'),
        is_active=False,
    )
    food = create_category(user, name='Alimentação')
    leisure = create_category(user, name='Lazer')
    salary = create_category(user, name='Salário', category_type=INCOME)
    create_category(user, name='Transporte')

    def add(category, amount, day, account=main, description='Compra'):
        create_transaction(
            user, account=account, category=category,
            amount=Decimal(amount) * scale, date=day,
            description=description,
        )

    add(salary, '3000.00', date(2026, 8, 5), description='Salário')
    add(food, '700.00', date(2026, 8, 10))
    add(leisure, '300.00', date(2026, 8, 12))
    add(salary, '3000.00', date(2026, 9, 5), description='Salário')
    add(food, '1000.00', date(2026, 9, 8), description='Mercado do mês')
    add(food, '500.00', date(2026, 9, 9), account=savings,
        description='Feira')
    add(leisure, '500.00', date(2026, 9, 15), description='Cinema')
    add(food, '999.00', date(2026, 5, 20), description='Fora do período')


class ToolTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='outro@example.com')
        seed_user(cls.user)
        seed_user(cls.other, scale=7)

    def setUp(self):
        self.context = make_context(self.user, PERIOD_START, PERIOD_END)
        self.runtime = runtime_for(self.context)

    def call(self, tool, **args):
        return tool.invoke({**args, 'runtime': self.runtime})


class FinancialOverviewToolTests(ToolTestMixin, TestCase):
    def test_monthly_values_and_totals(self):
        result = self.call(get_financial_overview)

        self.assertEqual(result['period_start'], '2026-06-01')
        self.assertEqual(result['period_end'], '2026-09-20')
        self.assertEqual(result['reference_month'], '2026-09')
        self.assertFalse(result['reference_month_complete'])
        self.assertEqual(
            [month['month'] for month in result['months']],
            ['2026-06', '2026-07', '2026-08', '2026-09'],
        )
        june, _, august, september = result['months']
        self.assertEqual(june, {
            'month': '2026-06',
            'income': '0.00',
            'expense': '0.00',
            'result': '0.00',
            'savings_rate_percent': None,
            'transaction_count': 0,
        })
        self.assertEqual(august['income'], '3000.00')
        self.assertEqual(august['expense'], '1000.00')
        self.assertEqual(august['result'], '2000.00')
        self.assertEqual(august['savings_rate_percent'], 66.7)
        self.assertEqual(august['transaction_count'], 3)
        self.assertEqual(september['expense'], '2000.00')
        self.assertEqual(september['savings_rate_percent'], 33.3)
        self.assertEqual(september['transaction_count'], 4)
        self.assertEqual(result['totals'], {
            'income': '6000.00',
            'expense': '3000.00',
            'result': '3000.00',
            'savings_rate_percent': 50.0,
        })

    def test_total_balance_uses_only_active_accounts(self):
        # Main: 1000 + 6000 - 3499 (includes May) = 3501;
        # Poupança: 500 - 500 = 0. The inactive account is ignored.
        result = self.call(get_financial_overview)

        self.assertEqual(result['total_balance'], '3501.00')

    def test_complete_reference_month(self):
        self.runtime = runtime_for(
            make_context(self.user, PERIOD_START, date(2026, 9, 30))
        )

        result = self.call(get_financial_overview)

        self.assertTrue(result['reference_month_complete'])

    def test_period_across_year_boundary(self):
        self.runtime = runtime_for(
            make_context(self.user, date(2025, 11, 1), date(2026, 2, 10))
        )

        result = self.call(get_financial_overview)

        self.assertEqual(
            [month['month'] for month in result['months']],
            ['2025-11', '2025-12', '2026-01', '2026-02'],
        )


class CategoryBreakdownToolTests(ToolTestMixin, TestCase):
    def test_expense_breakdown_sorted_with_percent(self):
        result = self.call(get_category_breakdown, month='2026-09')

        self.assertEqual(result['month'], '2026-09')
        self.assertEqual(result['category_type'], 'expense')
        self.assertEqual(result['total'], '2000.00')
        self.assertEqual(result['categories'], [
            {
                'name': 'Alimentação', 'total': '1500.00',
                'percent': 75.0, 'transaction_count': 2,
            },
            {
                'name': 'Lazer', 'total': '500.00',
                'percent': 25.0, 'transaction_count': 1,
            },
        ])

    def test_income_breakdown(self):
        result = self.call(
            get_category_breakdown, month='2026-08', category_type='income',
        )

        self.assertEqual(result['categories'], [{
            'name': 'Salário', 'total': '3000.00',
            'percent': 100.0, 'transaction_count': 1,
        }])

    def test_month_without_transactions(self):
        result = self.call(get_category_breakdown, month='2026-06')

        self.assertEqual(result['total'], '0.00')
        self.assertEqual(result['categories'], [])

    def test_invalid_month_returns_error(self):
        for month in ('09/2026', '2026-9', '', 'abc', '2026-13', '2026-00'):
            with self.subTest(month=month):
                result = self.call(get_category_breakdown, month=month)
                self.assertIn('error', result)

    def test_month_outside_period_returns_error(self):
        for month in ('2026-05', '2026-10'):
            with self.subTest(month=month):
                result = self.call(get_category_breakdown, month=month)
                self.assertIn('outside the analysed period', result['error'])

    def test_invalid_category_type_returns_error(self):
        result = get_category_breakdown.func(
            month='2026-09', runtime=self.runtime, category_type='other',
        )

        self.assertIn('error', result)


class LargestTransactionsToolTests(ToolTestMixin, TestCase):
    def test_largest_expenses_sorted(self):
        result = self.call(get_largest_transactions, month='2026-09')

        self.assertEqual(result['month'], '2026-09')
        self.assertEqual(result['transaction_type'], 'expense')
        self.assertEqual(result['transactions'][0], {
            'date': '2026-09-08',
            'description': 'Mercado do mês',
            'amount': '1000.00',
            'category': 'Alimentação',
            'account': 'Conta Principal',
        })
        self.assertEqual(
            [row['amount'] for row in result['transactions']],
            ['1000.00', '500.00', '500.00'],
        )

    def test_limit_and_income(self):
        result = self.call(
            get_largest_transactions, month='2026-09',
            transaction_type='income', limit=1,
        )

        self.assertEqual(len(result['transactions']), 1)
        self.assertEqual(result['transactions'][0]['category'], 'Salário')

    def test_limit_must_be_between_1_and_10(self):
        for limit in (0, 11, -1):
            with self.subTest(limit=limit):
                result = self.call(
                    get_largest_transactions, month='2026-09', limit=limit,
                )
                self.assertEqual(
                    result, {'error': 'limit must be an integer from 1 to 10.'}
                )
        result = self.call(
            get_largest_transactions, month='2026-09', limit=10,
        )
        self.assertNotIn('error', result)

    def test_limit_rejects_non_integer(self):
        result = get_largest_transactions.func(
            month='2026-09', runtime=self.runtime, limit=True,
        )

        self.assertIn('error', result)

    def test_invalid_month_and_type_return_error(self):
        self.assertIn(
            'error', self.call(get_largest_transactions, month='setembro')
        )
        result = get_largest_transactions.func(
            month='2026-09', runtime=self.runtime, transaction_type='x',
        )
        self.assertIn('error', result)

    def test_description_is_truncated(self):
        create_transaction(
            self.user,
            account=create_account(self.user, name='Extra'),
            category=Category.objects.get(user=self.user, name='Lazer'),
            amount=Decimal('5000.00'),
            date=date(2026, 9, 18),
            description='x' * 150,
        )

        result = self.call(get_largest_transactions, month='2026-09')

        self.assertEqual(len(result['transactions'][0]['description']), 100)

    def test_does_not_expose_personal_data_or_ids(self):
        result = self.call(get_largest_transactions, month='2026-09')

        payload = json.dumps(result)
        self.assertNotIn('user@example.com', payload)
        self.assertNotIn('"id"', payload)
        self.assertNotIn('user_id', payload)


class CategoriesAndBalancesToolTests(ToolTestMixin, TestCase):
    def test_categories_with_usage_in_period(self):
        result = self.call(get_categories)

        self.assertEqual(result['categories'], [
            {
                'name': 'Alimentação', 'category_type': 'expense',
                'transaction_count': 3,
            },
            {
                'name': 'Lazer', 'category_type': 'expense',
                'transaction_count': 2,
            },
            {
                'name': 'Transporte', 'category_type': 'expense',
                'transaction_count': 0,
            },
            {
                'name': 'Salário', 'category_type': 'income',
                'transaction_count': 2,
            },
        ])

    def test_account_balances(self):
        result = self.call(get_account_balances)

        self.assertEqual(result, {
            'accounts': [
                {
                    'name': 'Conta Principal',
                    'account_type': 'Conta corrente',
                    'balance': '3501.00',
                },
                {
                    'name': 'Poupança',
                    'account_type': 'Poupança',
                    'balance': '0.00',
                },
            ],
            'total_balance': '3501.00',
        })


class ToolSchemaTests(TestCase):
    def test_runtime_and_user_are_hidden_from_model(self):
        for tool in ANALYSIS_TOOLS:
            with self.subTest(tool=tool.name):
                schema = tool.tool_call_schema.model_json_schema()
                properties = schema.get('properties', {})
                self.assertNotIn('runtime', properties)
                self.assertNotIn('user_id', properties)
                self.assertNotIn('email', properties)
                self.assertNotIn('period_start', properties)
                self.assertTrue(tool.description)

    def test_limit_and_type_arguments(self):
        schema = get_largest_transactions.tool_call_schema.model_json_schema()

        self.assertEqual(
            set(schema['properties']),
            {'month', 'transaction_type', 'limit'},
        )
        self.assertEqual(
            schema['properties']['transaction_type']['enum'],
            ['income', 'expense'],
        )


class ReadOnlyGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.transaction = create_transaction(cls.user)

    def assert_blocked(self, write):
        # The savepoint is opened outside the guard, so the failed
        # statement only rolls back this block.
        with self.assertRaises(ReadOnlyQueryError):
            with transaction.atomic():
                with read_only_queries():
                    write()

    def test_blocks_update_insert_and_delete(self):
        user_transactions = Transaction.objects.filter(user=self.user)
        self.assert_blocked(
            lambda: user_transactions.update(amount=Decimal('1.00'))
        )
        self.assert_blocked(lambda: create_category(self.user, name='Nova'))
        self.assert_blocked(user_transactions.delete)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.amount, Decimal('100.00'))
        self.assertFalse(
            Category.objects.filter(user=self.user, name='Nova').exists()
        )

    def test_allows_select(self):
        with read_only_queries():
            self.assertEqual(
                Transaction.objects.filter(user=self.user).count(), 1
            )

    def test_guard_is_removed_after_block(self):
        with read_only_queries():
            pass

        Transaction.objects.filter(user=self.user).update(
            amount=Decimal('2.00')
        )
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.amount, Decimal('2.00'))


class ToolIsolationTests(ToolTestMixin, TestCase):
    """Each tool returns only data of the context user."""

    def test_each_tool_only_sees_context_user(self):
        other_runtime = runtime_for(
            make_context(self.other, PERIOD_START, PERIOD_END)
        )
        overview = self.call(get_financial_overview)
        other_overview = get_financial_overview.invoke(
            {'runtime': other_runtime}
        )

        self.assertEqual(overview['totals']['expense'], '3000.00')
        self.assertEqual(other_overview['totals']['expense'], '21000.00')
        breakdown = self.call(get_category_breakdown, month='2026-09')
        self.assertEqual(breakdown['total'], '2000.00')
        largest = self.call(get_largest_transactions, month='2026-09')
        self.assertEqual(largest['transactions'][0]['amount'], '1000.00')
        self.assertEqual(len(self.call(get_categories)['categories']), 4)
        balances = self.call(get_account_balances)
        self.assertEqual(balances['total_balance'], '3501.00')
        self.assertEqual(len(balances['accounts']), 2)

    def test_user_id_sent_by_model_is_ignored(self):
        other_id = self.other.pk
        calls = [
            ('get_financial_overview', {'user_id': other_id}),
            (
                'get_category_breakdown',
                {'month': '2026-09', 'user_id': other_id},
            ),
            (
                'get_largest_transactions',
                {'month': '2026-09', 'user_id': other_id, 'limit': 10},
            ),
            ('get_categories', {'user_id': other_id}),
            ('get_account_balances', {'user_id': other_id}),
        ]
        model = fake_model(
            *[tool_call_message(name, args) for name, args in calls],
            structured_response_message(),
        )
        agent = build_agent(model)

        with share_connection_with_tools():
            result = agent.invoke(
                {'messages': [{'role': 'user', 'content': 'Analise.'}]},
                context=self.context,
            )

        outputs = {
            message.name: json.loads(message.content)
            for message in result['messages']
            if isinstance(message, ToolMessage)
            and message.name != 'FinancialAnalysis'
        }
        self.assertEqual(len(outputs), 5)
        self.assertEqual(
            outputs['get_financial_overview']['totals']['expense'],
            '3000.00',
        )
        self.assertEqual(
            outputs['get_category_breakdown']['total'], '2000.00'
        )
        self.assertEqual(
            [
                row['amount'] for row in
                outputs['get_largest_transactions']['transactions']
            ],
            ['1000.00', '500.00', '500.00'],
        )
        self.assertEqual(len(outputs['get_categories']['categories']), 4)
        self.assertEqual(
            outputs['get_account_balances']['total_balance'], '3501.00'
        )
