from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.tests.utils import patch_chat_model, silence_ai_logger
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)
from transactions.models import Transaction

LAST_DAY = date(2026, 9, 30)
OTHER_DAY = date(2026, 9, 29)
SEPTEMBER = date(2026, 9, 1)


def create_transactions(user, day=date(2026, 9, 10), quantity=5):
    account = create_account(user)
    category = create_category(user)
    for _ in range(quantity):
        create_transaction(
            user, account=account, category=category, date=day,
            amount=Decimal('10.00'),
        )


@override_settings(OPENAI_API_KEY='test-key', AI_ANALYSIS_ENABLED=True)
class GenerateMonthlyAnalysesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = create_user(email='alice@example.com')
        cls.bruno = create_user(email='bruno@example.com')
        cls.inactive = create_user(
            email='inativo@example.com', is_active=False,
        )
        cls.disabled = create_user(email='desativado@example.com')
        cls.disabled.profile.ai_analysis_enabled = False
        cls.disabled.profile.save()
        for user in (cls.alice, cls.bruno, cls.inactive, cls.disabled):
            create_transactions(user)

    def setUp(self):
        silence_ai_logger(self)

    def run_command(self, today, *args):
        stdout = StringIO()
        with mock.patch(
            'django.utils.timezone.localdate', return_value=today,
        ):
            call_command('generate_monthly_analyses', *args, stdout=stdout)
        return stdout.getvalue()

    def analysed_users(self, month=SEPTEMBER):
        return set(
            MonthlyAnalysis.objects.filter(
                reference_month=month, status=AnalysisStatus.COMPLETED,
            ).values_list('user__email', flat=True)
        )

    def test_last_day_generates_for_active_enabled_users(self):
        with patch_chat_model() as get_model:
            output = self.run_command(LAST_DAY)

        self.assertEqual(get_model.call_count, 2)
        self.assertEqual(
            self.analysed_users(),
            {'alice@example.com', 'bruno@example.com'},
        )
        analysis = MonthlyAnalysis.objects.get(user=self.alice)
        self.assertEqual(analysis.period_start, date(2026, 6, 1))
        self.assertEqual(analysis.period_end, LAST_DAY)
        self.assertIn('Gerando análises de setembro de 2026...', output)
        self.assertIn('Concluídas: 2', output)
        self.assertIn('Desativadas pelo usuário: 1', output)
        self.assertNotIn('alice@example.com', output)

    def test_ignores_inactive_and_disabled_users(self):
        with patch_chat_model():
            self.run_command(LAST_DAY)

        self.assertFalse(
            MonthlyAnalysis.objects.filter(
                user__in=[self.inactive, self.disabled]
            ).exists()
        )

    def test_other_days_do_nothing(self):
        for day in (OTHER_DAY, date(2026, 9, 1), date(2026, 9, 15)):
            with self.subTest(day=day):
                with patch_chat_model() as get_model:
                    output = self.run_command(day)

                get_model.assert_not_called()
                self.assertIn(
                    'Hoje não é o último dia do mês; nada a fazer.', output
                )
                self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_last_day_of_february(self):
        february = date(2026, 2, 1)
        user = create_user(email='fev@example.com')
        MonthlyAnalysis.objects.all().delete()
        create_transactions(user, date(2026, 2, 10))

        with patch_chat_model():
            self.run_command(date(2026, 2, 28), '--user', user.email)

        self.assertEqual(self.analysed_users(february), {'fev@example.com'})

    def test_is_idempotent(self):
        with patch_chat_model() as get_model:
            self.run_command(LAST_DAY)
            output = self.run_command(LAST_DAY)

        self.assertEqual(get_model.call_count, 2)
        self.assertEqual(MonthlyAnalysis.objects.count(), 2)
        self.assertEqual(
            set(
                MonthlyAnalysis.objects.values_list('attempts', flat=True)
            ),
            {1},
        )
        self.assertIn('Já existentes: 2', output)

    def test_reference_month_computed_once_across_midnight(self):
        stdout = StringIO()
        with mock.patch(
            'django.utils.timezone.localdate',
            side_effect=[LAST_DAY] + [date(2026, 10, 1)] * 20,
        ):
            with patch_chat_model():
                call_command('generate_monthly_analyses', stdout=stdout)

        self.assertEqual(
            self.analysed_users(),
            {'alice@example.com', 'bruno@example.com'},
        )
        self.assertFalse(
            MonthlyAnalysis.objects.filter(
                reference_month=date(2026, 10, 1)
            ).exists()
        )
        analysis = MonthlyAnalysis.objects.get(user=self.alice)
        self.assertEqual(analysis.period_end, LAST_DAY)

    def test_month_option_accepts_closed_month(self):
        august = date(2026, 8, 1)
        Transaction.objects.update(date=date(2026, 8, 5))

        with patch_chat_model():
            output = self.run_command(OTHER_DAY, '--month', '2026-08')

        self.assertEqual(
            self.analysed_users(august),
            {'alice@example.com', 'bruno@example.com'},
        )
        analysis = MonthlyAnalysis.objects.get(
            user=self.alice, reference_month=august,
        )
        self.assertEqual(analysis.period_start, date(2026, 5, 1))
        self.assertEqual(analysis.period_end, date(2026, 8, 31))
        self.assertIn('agosto de 2026', output)

    def test_month_option_rejects_current_and_future_months(self):
        for value in ('2026-09', '2026-10', '2027-01'):
            with self.subTest(month=value):
                with patch_chat_model() as get_model:
                    with self.assertRaisesMessage(
                        CommandError, 'Informe um mês já encerrado',
                    ):
                        self.run_command(LAST_DAY, '--month', value)
                get_model.assert_not_called()
        self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_month_option_rejects_invalid_format(self):
        for value in ('09/2026', '2026-13', 'agosto'):
            with self.subTest(month=value):
                with self.assertRaisesMessage(CommandError, 'Mês inválido'):
                    self.run_command(LAST_DAY, '--month', value)

    def test_user_option(self):
        with patch_chat_model() as get_model:
            output = self.run_command(
                LAST_DAY, '--user', 'alice@example.com', '--verbosity', '2',
            )

        get_model.assert_called_once_with()
        self.assertEqual(self.analysed_users(), {'alice@example.com'})
        self.assertIn(f'Usuário {self.alice.pk}: Concluídas', output)

    def test_user_option_rejects_unknown_or_inactive_user(self):
        for email in ('ninguem@example.com', 'inativo@example.com'):
            with self.subTest(email=email):
                with self.assertRaisesMessage(
                    CommandError, 'Nenhum usuário ativo',
                ):
                    self.run_command(LAST_DAY, '--user', email)

    @override_settings(OPENAI_API_KEY='', AI_ANALYSIS_ENABLED=False)
    def test_fails_without_api_key(self):
        with patch_chat_model() as get_model:
            with self.assertRaisesMessage(
                CommandError, 'A análise com IA está desativada',
            ):
                self.run_command(LAST_DAY)

        get_model.assert_not_called()
        self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_summary_reports_failures(self):
        with patch_chat_model():
            with mock.patch(
                'ai.services.run_analysis',
                side_effect=RuntimeError('falhou'),
            ):
                output = self.run_command(LAST_DAY)

        self.assertIn('Falhas: 2', output)
        self.assertEqual(
            MonthlyAnalysis.objects.filter(
                status=AnalysisStatus.FAILED
            ).count(),
            2,
        )

    def test_without_active_users(self):
        get_user_model().objects.update(is_active=False)

        output = self.run_command(LAST_DAY)

        self.assertIn('Nenhum usuário ativo encontrado.', output)
