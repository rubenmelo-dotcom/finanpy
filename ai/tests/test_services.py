from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import httpx
import openai
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from langchain.agents.structured_output import (
    StructuredOutputValidationError,
)
from langchain.messages import AIMessage
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from ai import services
from ai.agent import AnalysisGenerationError
from ai.constants import AI_MAX_ATTEMPTS, AI_STALE_AFTER
from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.schemas import SCHEMA_VERSION, FinancialAnalysis
from ai.services import (
    GenerationOutcome,
    add_months,
    analysis_period,
    current_month_state,
    error_message,
    generate_monthly_analysis,
    is_last_day_of_month,
    month_end,
    month_label,
    parse_month_param,
)
from ai.tests.utils import (
    analysis_payload,
    create_analysis,
    fake_model,
    patch_chat_model,
    silence_ai_logger,
    structured_response_message,
    tool_call_message,
)
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)

TODAY = date(2026, 9, 20)
CURRENT_MONTH = date(2026, 9, 1)
TEST_KEY = 'sk-test-key-0123456789'
OPENAI_REQUEST = httpx.Request('POST', 'https://api.openai.com/v1/chat')


def create_transactions(user, quantity, day=TODAY):
    account = create_account(user)
    category = create_category(user)
    for _ in range(quantity):
        create_transaction(
            user, account=account, category=category, date=day,
            amount=Decimal('10.00'),
        )


def valid_result(input_tokens=10, output_tokens=5):
    usage = {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
    }
    return FinancialAnalysis(**analysis_payload()), usage


@override_settings(OPENAI_API_KEY=TEST_KEY, AI_ANALYSIS_ENABLED=True)
class ServiceTestCase(TestCase):
    """Base: fixed date (2026-09-20) and user with 5 transactions."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        create_transactions(cls.user, 5)

    def setUp(self):
        patcher = mock.patch(
            'django.utils.timezone.localdate', return_value=TODAY
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        silence_ai_logger(self)

    def get_analysis(self, user=None, month=CURRENT_MONTH):
        return MonthlyAnalysis.objects.get(
            user=user or self.user, reference_month=month
        )


class GenerationSuccessTests(ServiceTestCase):
    def test_successful_generation(self):
        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_called_once_with()
        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        analysis = self.get_analysis()
        self.assertEqual(result.analysis, analysis)
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED)
        self.assertEqual(analysis.content, analysis_payload())
        self.assertEqual(analysis.summary, analysis_payload()['summary'])
        self.assertEqual(analysis.schema_version, SCHEMA_VERSION)
        self.assertEqual(analysis.model_name, 'fake-model')
        self.assertEqual(analysis.attempts, 1)
        self.assertEqual(analysis.input_tokens, 200)
        self.assertEqual(analysis.output_tokens, 40)
        self.assertEqual(analysis.total_tokens, 240)
        self.assertEqual(analysis.error_message, '')
        self.assertIsNotNone(analysis.generated_at)

    def test_period_is_three_previous_months_until_today(self):
        with patch_chat_model():
            generate_monthly_analysis(self.user)

        analysis = self.get_analysis()
        self.assertEqual(analysis.period_start, date(2026, 6, 1))
        self.assertEqual(analysis.period_end, TODAY)

    def test_closed_month_uses_last_day_as_period_end(self):
        user = create_user(email='agosto@example.com')
        create_transactions(user, 5, date(2026, 8, 10))

        with patch_chat_model():
            result = generate_monthly_analysis(user, date(2026, 8, 15))

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        analysis = self.get_analysis(user, date(2026, 8, 1))
        self.assertEqual(analysis.period_start, date(2026, 5, 1))
        self.assertEqual(analysis.period_end, date(2026, 8, 31))

    def test_future_reference_month_raises(self):
        with patch_chat_model() as get_model:
            with self.assertRaises(ValueError):
                generate_monthly_analysis(self.user, date(2026, 10, 1))

        get_model.assert_not_called()

    def test_runs_real_agent_with_tools_and_fake_model(self):
        model = fake_model(
            tool_call_message('get_financial_overview'),
            tool_call_message(
                'get_largest_transactions', {'month': '2026-09'},
            ),
            structured_response_message(
                usage_metadata={'input_tokens': 50, 'output_tokens': 7},
            ),
        )

        with patch_chat_model(model):
            result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        self.assertEqual(result.analysis.total_tokens, 297)

    def test_logs_without_email_or_values(self):
        with self.assertLogs('ai', level='INFO') as logs:
            with patch_chat_model():
                generate_monthly_analysis(self.user)

        output = '\n'.join(logs.output)
        self.assertIn(f'user_id={self.user.pk}', output)
        self.assertIn('month=2026-09', output)
        self.assertIn('total_tokens=240', output)
        self.assertNotIn(self.user.email, output)
        self.assertNotIn('10.00', output)


class GenerationSkipTests(ServiceTestCase):
    def test_insufficient_data_does_not_call_llm(self):
        user = create_user(email='poucos@example.com')
        create_transactions(user, 4)

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.INSUFFICIENT_DATA)
        analysis = self.get_analysis(user)
        self.assertEqual(analysis.status, AnalysisStatus.INSUFFICIENT_DATA)
        self.assertEqual(analysis.attempts, 0)

    def test_transactions_outside_period_do_not_count(self):
        user = create_user(email='antigo@example.com')
        create_transactions(user, 5, date(2026, 5, 31))

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.INSUFFICIENT_DATA)

    def test_insufficient_data_can_be_requested_again(self):
        user = create_user(email='poucos@example.com')
        create_transactions(user, 4)
        with patch_chat_model():
            generate_monthly_analysis(user)
        create_transaction(
            user,
            account=user.accounts.get(),
            category=user.categories.get(),
            date=TODAY,
        )

        with patch_chat_model():
            result = generate_monthly_analysis(user)

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)

    def test_user_disabled_creates_nothing_and_does_not_call_llm(self):
        self.user.profile.ai_analysis_enabled = False
        self.user.profile.save()

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.USER_DISABLED)
        self.assertIsNone(result.analysis)
        self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_user_without_profile_counts_as_disabled(self):
        self.user.profile.delete()

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.USER_DISABLED)

    def test_user_disables_after_reservation(self):
        # Preference checked again right before calling the LLM.
        with mock.patch(
            'ai.services._user_allows_ai', side_effect=[True, False],
        ):
            with patch_chat_model() as get_model:
                result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.USER_DISABLED)
        analysis = self.get_analysis()
        self.assertEqual(analysis.status, AnalysisStatus.PENDING)
        self.assertEqual(analysis.attempts, 0)
        self.assertIsNone(analysis.started_at)

    @override_settings(OPENAI_API_KEY='')
    def test_feature_disabled_without_key(self):
        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.FEATURE_DISABLED)
        self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_improperly_configured_model_resets_to_pending(self):
        with patch_chat_model(
            side_effect=ImproperlyConfigured('sem chave')
        ):
            result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.FEATURE_DISABLED)
        analysis = self.get_analysis()
        self.assertEqual(analysis.status, AnalysisStatus.PENDING)
        self.assertEqual(analysis.attempts, 0)

    def test_completed_analysis_is_not_regenerated(self):
        existing = create_analysis(self.user, CURRENT_MONTH, total_tokens=9)

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.ALREADY_COMPLETED)
        existing.refresh_from_db()
        self.assertEqual(existing.total_tokens, 9)
        self.assertEqual(existing.attempts, 0)


class GenerationFailureTests(ServiceTestCase):
    def fail_with(self, exc):
        with patch_chat_model() as get_model:
            with mock.patch(
                'ai.services.run_analysis', side_effect=exc,
            ) as run:
                result = generate_monthly_analysis(self.user)
        get_model.assert_called_once_with()
        run.assert_called_once()
        return result

    def test_failure_records_failed_and_increments_attempts(self):
        result = self.fail_with(
            openai.APITimeoutError(request=OPENAI_REQUEST)
        )

        self.assertEqual(result.outcome, GenerationOutcome.FAILED)
        analysis = self.get_analysis()
        self.assertEqual(analysis.status, AnalysisStatus.FAILED)
        self.assertEqual(analysis.attempts, 1)
        self.assertTrue(
            analysis.error_message.startswith('APITimeoutError:')
        )
        self.assertTrue(analysis.can_retry)

    def test_failed_analysis_can_be_retried(self):
        self.fail_with(openai.APIConnectionError(request=OPENAI_REQUEST))

        with patch_chat_model():
            result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        analysis = self.get_analysis()
        self.assertEqual(analysis.attempts, 2)
        self.assertEqual(analysis.error_message, '')

    def test_attempt_limit(self):
        for attempt in range(1, AI_MAX_ATTEMPTS + 1):
            result = self.fail_with(RuntimeError('falhou'))
            self.assertEqual(result.outcome, GenerationOutcome.FAILED)
            self.assertEqual(self.get_analysis().attempts, attempt)

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(
            result.outcome, GenerationOutcome.ATTEMPTS_EXHAUSTED
        )
        analysis = self.get_analysis()
        self.assertEqual(analysis.attempts, AI_MAX_ATTEMPTS)
        self.assertFalse(analysis.can_retry)

    def test_openai_errors_are_logged_by_severity(self):
        response = httpx.Response(401, request=OPENAI_REQUEST)
        cases = [
            (
                openai.AuthenticationError(
                    'invalid', response=response, body=None,
                ),
                'ERROR',
            ),
            (
                openai.RateLimitError(
                    'limit',
                    response=httpx.Response(429, request=OPENAI_REQUEST),
                    body=None,
                ),
                'WARNING',
            ),
            (GraphRecursionError('loop'), 'WARNING'),
            (AnalysisGenerationError('no output'), 'WARNING'),
            (RuntimeError('boom'), 'ERROR'),
        ]
        for exc, level in cases:
            with self.subTest(error=type(exc).__name__):
                MonthlyAnalysis.objects.all().delete()
                with self.assertLogs('ai', level='WARNING') as logs:
                    result = self.fail_with(exc)
                self.assertEqual(result.outcome, GenerationOutcome.FAILED)
                self.assertTrue(
                    any(
                        record.levelname == level
                        and type(exc).__name__ in record.getMessage()
                        for record in logs.records
                    )
                )

    def test_error_message_never_contains_api_key(self):
        exc = openai.AuthenticationError(
            f'Incorrect API key provided: {TEST_KEY} or sk-other12345',
            response=httpx.Response(401, request=OPENAI_REQUEST),
            body=None,
        )

        self.fail_with(exc)

        message = self.get_analysis().error_message
        self.assertTrue(message.startswith('AuthenticationError:'))
        self.assertNotIn(TEST_KEY, message)
        self.assertNotIn('sk-other12345', message)
        self.assertIn('***', message)

    def test_unexpected_error_after_reservation_records_failed(self):
        with patch_chat_model():
            with mock.patch(
                'ai.services.AnalysisContext',
                side_effect=RuntimeError('db'),
            ):
                result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.FAILED)
        self.assertEqual(self.get_analysis().status, AnalysisStatus.FAILED)

    def test_unexpected_error_before_record_never_raises(self):
        with mock.patch(
            'ai.services._user_allows_ai', side_effect=RuntimeError('db'),
        ):
            with self.assertLogs('ai', level='ERROR'):
                result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.FAILED)
        self.assertIsNone(result.analysis)


class GenerationConcurrencyTests(ServiceTestCase):
    def test_second_call_during_generation_does_not_generate(self):
        inner = {}

        def slow_analysis(context, model=None):
            # Another request arrives while the LLM is still running.
            inner['result'] = generate_monthly_analysis(self.user)
            return valid_result()

        with patch_chat_model() as get_model:
            with mock.patch(
                'ai.services.run_analysis', side_effect=slow_analysis,
            ):
                result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        self.assertEqual(
            inner['result'].outcome, GenerationOutcome.IN_PROGRESS
        )
        get_model.assert_called_once_with()
        analysis = self.get_analysis()
        self.assertEqual(analysis.attempts, 1)
        self.assertEqual(MonthlyAnalysis.objects.count(), 1)

    def test_processing_record_is_not_generated_again(self):
        create_analysis(
            self.user, CURRENT_MONTH,
            status=AnalysisStatus.PROCESSING,
            started_at=timezone.now() - timedelta(minutes=2),
        )

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_not_called()
        self.assertEqual(result.outcome, GenerationOutcome.IN_PROGRESS)

    def test_stale_processing_is_taken_over(self):
        create_analysis(
            self.user, CURRENT_MONTH,
            status=AnalysisStatus.PROCESSING,
            started_at=timezone.now() - AI_STALE_AFTER - timedelta(
                minutes=1
            ),
            attempts=1,
        )

        with patch_chat_model() as get_model:
            result = generate_monthly_analysis(self.user)

        get_model.assert_called_once_with()
        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        analysis = self.get_analysis()
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED)
        self.assertEqual(analysis.attempts, 2)

    def test_result_discarded_when_row_was_taken_over(self):
        def taken_over(context, model=None):
            MonthlyAnalysis.objects.filter(user=self.user).update(
                started_at=timezone.now() + timedelta(seconds=1)
            )
            return valid_result()

        with patch_chat_model():
            with mock.patch(
                'ai.services.run_analysis', side_effect=taken_over,
            ):
                with self.assertLogs('ai', level='WARNING'):
                    result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.IN_PROGRESS)
        analysis = self.get_analysis()
        self.assertEqual(analysis.status, AnalysisStatus.PROCESSING)
        self.assertIsNone(analysis.content)

    def test_row_created_concurrently_is_reused(self):
        # Another process inserted the row between the SELECT and the
        # INSERT of get_or_create().
        existing = create_analysis(
            self.user, CURRENT_MONTH, status=AnalysisStatus.PENDING,
        )

        with mock.patch.object(
            type(MonthlyAnalysis.objects), 'get_or_create',
            side_effect=IntegrityError('unique_analysis_per_user_month'),
        ):
            with patch_chat_model():
                result = generate_monthly_analysis(self.user)

        self.assertEqual(result.outcome, GenerationOutcome.COMPLETED)
        self.assertEqual(result.analysis.pk, existing.pk)
        self.assertEqual(MonthlyAnalysis.objects.count(), 1)


class ErrorMessageTests(TestCase):
    def validation_error(self):
        try:
            FinancialAnalysis(**analysis_payload(summary='x' * 700))
        except ValidationError as exc:
            return exc
        raise AssertionError('ValidationError expected')

    def test_validation_error_without_input_values(self):
        message = error_message(self.validation_error())

        self.assertTrue(message.startswith('ValidationError: summary:'))
        self.assertNotIn('xxxx', message)

    def test_structured_output_error_uses_source(self):
        exc = StructuredOutputValidationError(
            'FinancialAnalysis', self.validation_error(),
            AIMessage(content=''),
        )

        message = error_message(exc)

        self.assertTrue(
            message.startswith('StructuredOutputValidationError: summary')
        )
        self.assertNotIn('xxxx', message)

    def test_structured_output_error_with_other_source(self):
        exc = StructuredOutputValidationError(
            'FinancialAnalysis', KeyError('x'), AIMessage(content=''),
        )

        self.assertEqual(
            error_message(exc), 'StructuredOutputValidationError: KeyError'
        )

    def test_message_is_truncated(self):
        message = error_message(RuntimeError('a' * 2000))

        self.assertEqual(len(message), len('RuntimeError: ') + 500)


class HelperTests(TestCase):
    def test_month_helpers(self):
        self.assertEqual(month_end(date(2028, 2, 10)), date(2028, 2, 29))
        self.assertTrue(is_last_day_of_month(date(2026, 9, 30)))
        self.assertFalse(is_last_day_of_month(date(2026, 9, 29)))
        self.assertEqual(add_months(date(2026, 2, 1), -3), date(2025, 11, 1))
        self.assertEqual(add_months(date(2026, 11, 1), 2), date(2027, 1, 1))
        self.assertEqual(month_label(date(2026, 3, 1)), 'março de 2026')

    def test_analysis_period(self):
        self.assertEqual(
            analysis_period(date(2026, 9, 1), date(2026, 9, 20)),
            (date(2026, 6, 1), date(2026, 9, 20)),
        )
        self.assertEqual(
            analysis_period(date(2026, 2, 1), date(2026, 9, 20)),
            (date(2025, 11, 1), date(2026, 2, 28)),
        )
        with self.assertRaises(ValueError):
            analysis_period(date(2026, 10, 1), date(2026, 9, 20))

    def test_parse_month_param(self):
        self.assertEqual(parse_month_param('2026-08'), date(2026, 8, 1))
        self.assertEqual(parse_month_param(' 2026-08 '), date(2026, 8, 1))
        for value in (None, '', '2026-8', '2026-13', 'abc', '08/2026'):
            with self.subTest(value=value):
                self.assertIsNone(parse_month_param(value))

    def test_current_month_state(self):
        now = timezone.now()
        user = create_user()

        def build(status, **extra):
            return MonthlyAnalysis(
                user=user, reference_month=CURRENT_MONTH, status=status,
                **extra,
            )

        self.assertEqual(current_month_state(None), 'pending')
        self.assertEqual(
            current_month_state(build(AnalysisStatus.PENDING)), 'pending'
        )
        self.assertEqual(
            current_month_state(
                build(AnalysisStatus.PROCESSING, started_at=now), now
            ),
            'processing',
        )
        self.assertEqual(
            current_month_state(
                build(
                    AnalysisStatus.PROCESSING,
                    started_at=now - AI_STALE_AFTER - timedelta(seconds=1),
                ),
                now,
            ),
            'pending',
        )
        self.assertEqual(
            current_month_state(build(AnalysisStatus.PROCESSING)),
            'pending',
        )
        self.assertEqual(
            current_month_state(build(AnalysisStatus.FAILED, attempts=1)),
            'failed',
        )
        self.assertEqual(
            current_month_state(
                build(AnalysisStatus.FAILED, attempts=AI_MAX_ATTEMPTS)
            ),
            'failed_final',
        )
        self.assertEqual(
            current_month_state(build(AnalysisStatus.COMPLETED)),
            'completed',
        )
        self.assertEqual(
            current_month_state(build(AnalysisStatus.INSUFFICIENT_DATA)),
            'insufficient_data',
        )

    @override_settings(OPENAI_API_KEY='')
    def test_is_ai_enabled_follows_key(self):
        self.assertFalse(services.is_ai_enabled())
        with override_settings(OPENAI_API_KEY='test-key'):
            self.assertTrue(services.is_ai_enabled())
