from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib import messages
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.services import GenerationOutcome, GenerationResult
from ai.tests.utils import (
    create_analysis,
    patch_chat_model,
    silence_ai_logger,
)
from core.test_utils import (
    create_account,
    create_category,
    create_transaction,
    create_user,
)

TODAY = date(2026, 9, 10)
CURRENT_MONTH = date(2026, 9, 1)
GENERATE_URL = reverse('ai:generate')
DASHBOARD_URL = reverse('dashboard')


def create_transactions(user, quantity=5):
    account = create_account(user)
    category = create_category(user)
    for _ in range(quantity):
        create_transaction(
            user, account=account, category=category, date=TODAY,
            amount=Decimal('10.00'),
        )


def response_messages(response):
    return [
        (message.level, str(message))
        for message in get_messages(response.wsgi_request)
    ]


@override_settings(OPENAI_API_KEY='test-key', AI_ANALYSIS_ENABLED=True)
class GenerateAnalysisViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        create_transactions(cls.user)

    def setUp(self):
        patcher = mock.patch(
            'django.utils.timezone.localdate', return_value=TODAY,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        silence_ai_logger(self)

    def test_post_requires_login(self):
        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        self.assertRedirects(
            response, f'{reverse("login")}?next={GENERATE_URL}',
        )
        get_model.assert_not_called()
        self.assertFalse(MonthlyAnalysis.objects.exists())

    def test_get_returns_405(self):
        self.client.force_login(self.user)

        with patch_chat_model() as get_model:
            response = self.client.get(GENERATE_URL)

        self.assertEqual(response.status_code, 405)
        get_model.assert_not_called()

    def test_post_any_day_generates_current_month(self):
        self.client.force_login(self.user)

        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        self.assertRedirects(response, DASHBOARD_URL)
        get_model.assert_called_once_with()
        analysis = MonthlyAnalysis.objects.get(user=self.user)
        self.assertEqual(analysis.reference_month, CURRENT_MONTH)
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED)
        self.assertEqual(analysis.period_end, TODAY)
        self.assertEqual(
            response_messages(response),
            [(messages.SUCCESS, 'Sua análise do mês está pronta.')],
        )

    def test_completed_month_does_not_call_llm(self):
        create_analysis(self.user, CURRENT_MONTH)
        self.client.force_login(self.user)

        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        get_model.assert_not_called()
        self.assertEqual(
            response_messages(response),
            [(messages.INFO, 'A análise deste mês já foi gerada.')],
        )
        self.assertEqual(MonthlyAnalysis.objects.count(), 1)

    def test_user_disabled_message(self):
        self.user.profile.ai_analysis_enabled = False
        self.user.profile.save()
        self.client.force_login(self.user)

        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        get_model.assert_not_called()
        self.assertFalse(MonthlyAnalysis.objects.exists())
        self.assertEqual(
            response_messages(response),
            [(
                messages.WARNING,
                'A análise com IA está desativada no seu perfil.',
            )],
        )

    def test_insufficient_data_message(self):
        user = create_user(email='novo@example.com')
        self.client.force_login(user)

        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        get_model.assert_not_called()
        self.assertEqual(
            response_messages(response),
            [(
                messages.WARNING,
                'Registre pelo menos 5 transações para gerar a análise.',
            )],
        )

    @override_settings(OPENAI_API_KEY='')
    def test_feature_disabled_message(self):
        self.client.force_login(self.user)

        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        get_model.assert_not_called()
        self.assertFalse(MonthlyAnalysis.objects.exists())
        self.assertEqual(
            response_messages(response),
            [(
                messages.ERROR,
                'A análise com IA não está disponível no momento.',
            )],
        )

    def test_message_for_each_outcome(self):
        expected = {
            GenerationOutcome.COMPLETED: (
                messages.SUCCESS, 'Sua análise do mês está pronta.',
            ),
            GenerationOutcome.ALREADY_COMPLETED: (
                messages.INFO, 'A análise deste mês já foi gerada.',
            ),
            GenerationOutcome.IN_PROGRESS: (
                messages.INFO,
                'Sua análise já está sendo gerada. Atualize a página em '
                'instantes.',
            ),
            GenerationOutcome.INSUFFICIENT_DATA: (
                messages.WARNING,
                'Registre pelo menos 5 transações para gerar a análise.',
            ),
            GenerationOutcome.FAILED: (
                messages.ERROR,
                'Não foi possível gerar sua análise agora. Tente novamente '
                'em alguns minutos.',
            ),
            GenerationOutcome.ATTEMPTS_EXHAUSTED: (
                messages.WARNING,
                'O limite de tentativas para gerar a análise deste mês foi '
                'atingido. Você pode consultar as análises anteriores.',
            ),
            GenerationOutcome.USER_DISABLED: (
                messages.WARNING,
                'A análise com IA está desativada no seu perfil.',
            ),
            GenerationOutcome.FEATURE_DISABLED: (
                messages.ERROR,
                'A análise com IA não está disponível no momento.',
            ),
        }
        self.assertEqual(set(expected), set(GenerationOutcome))
        self.client.force_login(self.user)
        for outcome, message in expected.items():
            with self.subTest(outcome=outcome):
                with mock.patch(
                    'ai.views.generate_monthly_analysis',
                    return_value=GenerationResult(outcome),
                ) as generate:
                    response = self.client.post(GENERATE_URL)

                generate.assert_called_once_with(self.user)
                self.assertRedirects(response, DASHBOARD_URL)
                self.assertEqual(response_messages(response), [message])

    def test_failure_message_from_real_service(self):
        self.client.force_login(self.user)

        with patch_chat_model():
            with mock.patch(
                'ai.services.run_analysis',
                side_effect=RuntimeError('falhou'),
            ):
                response = self.client.post(GENERATE_URL)

        self.assertEqual(response_messages(response)[0][0], messages.ERROR)
        self.assertEqual(
            MonthlyAnalysis.objects.get(user=self.user).status,
            AnalysisStatus.FAILED,
        )
