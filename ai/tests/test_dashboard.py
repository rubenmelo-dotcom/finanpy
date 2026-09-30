import re
from datetime import date, datetime, timedelta
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ai.constants import AI_MAX_ATTEMPTS, AI_STALE_AFTER
from ai.models import AnalysisStatus
from ai.services import dashboard_analysis_context
from ai.tests.utils import (
    analysis_payload,
    create_analysis,
    patch_chat_model,
    silence_ai_logger,
)
from core.test_utils import create_user

TODAY = date(2026, 9, 10)
SEPTEMBER = date(2026, 9, 1)
AUGUST = date(2026, 8, 1)
JULY = date(2026, 7, 1)
DASHBOARD_URL = reverse('dashboard')
GENERATE_URL = reverse('ai:generate')
GENERATE_ACTION = f'action="{reverse("ai:generate")}"'

CTA_TEXT = (
    'A análise de setembro de 2026 será gerada automaticamente em'
)
EMPTY_TITLE = 'Sua primeira análise'
PROCESSING_TEXT = (
    'Estamos gerando sua análise. Isso pode levar alguns segundos.'
)
INSUFFICIENT_TEXT = (
    'Ainda não há transações suficientes para gerar a análise de '
    'setembro de 2026. Registre pelo menos 5 transações e tente novamente.'
)
FAILED_TEXT = (
    'Não foi possível gerar sua análise agora. Tente novamente em alguns '
    'minutos.'
)
FAILED_FINAL_TEXT = (
    'Não conseguimos gerar a análise deste mês. Você pode consultar as '
    'análises anteriores.'
)
DISCLAIMER = (
    'com base nos seus lançamentos. Não substitui orientação financeira '
    'profissional.'
)


def analysis_with_summary(user, month, summary, **extra):
    return create_analysis(
        user, month, content=analysis_payload(summary=summary), **extra,
    )


@override_settings(OPENAI_API_KEY='test-key', AI_ANALYSIS_ENABLED=True)
class DashboardAnalysisTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='outro@example.com')

    def setUp(self):
        patcher = mock.patch(
            'django.utils.timezone.localdate', return_value=TODAY,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.user)

    def get(self, **params):
        response = self.client.get(DASHBOARD_URL, params)
        self.assertEqual(response.status_code, 200)
        return response


class DashboardAnalysisStateTests(DashboardAnalysisTestCase):
    @override_settings(OPENAI_API_KEY='', AI_ANALYSIS_ENABLED=False)
    def test_block_hidden_without_key(self):
        response = self.get()

        self.assertFalse(response.context['ai_enabled'])
        self.assertNotContains(response, 'id="analise"')
        self.assertNotContains(response, GENERATE_ACTION)

    def test_user_disabled_shows_compact_card(self):
        self.user.profile.ai_analysis_enabled = False
        self.user.profile.save()
        create_analysis(self.user, AUGUST)

        response = self.get()

        self.assertContains(response, 'A análise com IA está desativada.')
        self.assertContains(response, 'Ativar no perfil')
        self.assertContains(response, reverse('profiles:update'))
        self.assertNotContains(response, GENERATE_ACTION)
        self.assertNotContains(response, analysis_payload()['summary'])

    def test_no_analysis_yet_shows_cta_and_empty_state(self):
        response = self.get()

        self.assertContains(response, 'Análise de setembro de 2026')
        self.assertContains(response, CTA_TEXT)
        self.assertContains(response, '30/09/2026')
        self.assertContains(response, 'às 23:59. Se preferir, gere agora.')
        self.assertContains(response, GENERATE_ACTION)
        self.assertContains(response, 'Gerar análise')
        self.assertContains(response, EMPTY_TITLE)
        self.assertContains(
            response,
            'Receba insights e dicas personalizadas com base nos seus '
            'lançamentos.',
        )
        self.assertContains(response, 'Desativar análise com IA')

    def test_pending_record_shows_cta(self):
        create_analysis(self.user, SEPTEMBER, status=AnalysisStatus.PENDING)

        response = self.get()

        self.assertContains(response, CTA_TEXT)
        self.assertContains(response, GENERATE_ACTION)

    def test_current_month_completed_is_view_only(self):
        analysis_with_summary(
            self.user, SEPTEMBER, 'Resumo de setembro.',
            generated_at=timezone.make_aware(datetime(2026, 9, 8, 15, 0)),
        )

        response = self.get()

        self.assertEqual(response.context['current_month_state'], 'completed')
        self.assertFalse(response.context['can_generate'])
        self.assertNotContains(response, GENERATE_ACTION)
        self.assertNotContains(response, CTA_TEXT)
        self.assertContains(response, 'Análise de setembro de 2026')
        self.assertContains(response, 'Resumo de setembro.')
        self.assertContains(response, 'Saudável')
        self.assertContains(response, 'Poupança em alta')
        self.assertContains(response, 'Prioridade alta')
        self.assertContains(response, 'Prioridade baixa')
        self.assertContains(response, 'Gerada por IA em')
        self.assertContains(response, '08/09/2026')
        self.assertContains(response, DISCLAIMER)
        self.assertNotContains(response, EMPTY_TITLE)

    def test_previous_analysis_shown_below_current_month_cta(self):
        analysis_with_summary(self.user, AUGUST, 'Resumo de agosto.')

        response = self.get()

        self.assertContains(response, CTA_TEXT)
        self.assertContains(response, GENERATE_ACTION)
        self.assertContains(response, 'Análise de agosto de 2026')
        self.assertContains(response, 'Resumo de agosto.')
        self.assertNotContains(response, EMPTY_TITLE)

    def test_insufficient_data_state(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.INSUFFICIENT_DATA,
        )

        response = self.get()

        self.assertContains(response, INSUFFICIENT_TEXT)
        self.assertContains(response, 'Nova transação')
        self.assertContains(response, reverse('transactions:create'))
        self.assertContains(response, GENERATE_ACTION)

    def test_processing_state(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.PROCESSING,
            started_at=timezone.now(),
        )

        response = self.get()

        self.assertContains(response, PROCESSING_TEXT)
        self.assertContains(response, 'Atualizar')
        self.assertContains(response, 'animate-pulse')
        self.assertNotContains(response, GENERATE_ACTION)

    def test_stale_processing_shows_cta(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.PROCESSING,
            started_at=timezone.now() - AI_STALE_AFTER - timedelta(
                minutes=1
            ),
        )

        response = self.get()

        self.assertNotContains(response, PROCESSING_TEXT)
        self.assertContains(response, CTA_TEXT)
        self.assertContains(response, GENERATE_ACTION)

    def test_failed_with_retry(self):
        analysis_with_summary(self.user, AUGUST, 'Resumo de agosto.')
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.FAILED, attempts=1,
        )

        response = self.get()

        self.assertContains(response, FAILED_TEXT)
        self.assertContains(response, 'Tentar novamente')
        self.assertContains(response, GENERATE_ACTION)
        self.assertContains(response, 'Resumo de agosto.')

    def test_failed_without_retry(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.FAILED,
            attempts=AI_MAX_ATTEMPTS,
        )

        response = self.get()

        self.assertContains(response, FAILED_FINAL_TEXT)
        self.assertNotContains(response, 'Tentar novamente')
        self.assertNotContains(response, GENERATE_ACTION)

    def test_overall_status_badges(self):
        cases = {
            'attention': 'Atenção',
            'critical': 'Crítica',
        }
        for status, label in cases.items():
            with self.subTest(status=status):
                self.user.monthly_analyses.all().delete()
                create_analysis(
                    self.user, SEPTEMBER,
                    content=analysis_payload(overall_status=status),
                )

                response = self.get()

                self.assertContains(response, label)

    def test_generated_content_is_escaped(self):
        analysis_with_summary(
            self.user, SEPTEMBER, '<script>alert("x")</script>',
        )

        response = self.get()

        self.assertNotContains(response, '<script>alert')
        self.assertContains(response, '&lt;script&gt;alert')


class DashboardAnalysisSelectorTests(DashboardAnalysisTestCase):
    def setUp(self):
        super().setUp()
        analysis_with_summary(self.user, JULY, 'Resumo de julho.')
        analysis_with_summary(self.user, AUGUST, 'Resumo de agosto.')
        create_analysis(self.user, date(2026, 6, 1),
                        status=AnalysisStatus.FAILED, attempts=3)
        analysis_with_summary(
            self.other, SEPTEMBER, 'Resumo secreto do outro usuário.',
        )
        analysis_with_summary(
            self.other, date(2026, 5, 1), 'Maio do outro usuário.',
        )

    def test_selector_lists_only_own_completed_analyses(self):
        response = self.get()

        options = response.context['analysis_options']
        self.assertEqual(
            [option['value'] for option in options],
            ['2026-08', '2026-07'],
        )
        self.assertTrue(options[0]['is_latest'])
        self.assertTrue(options[0]['is_selected'])
        self.assertContains(response, 'Análise do mês')
        self.assertContains(response, 'name="analise"')
        self.assertContains(
            response, 'Agosto de 2026 (mais recente)</option>',
        )
        self.assertContains(response, 'Julho de 2026</option>')
        self.assertNotContains(response, 'value="2026-06"')
        self.assertNotContains(response, 'value="2026-05"')
        self.assertNotContains(response, 'value="2026-09"')

    def test_selector_hidden_with_single_analysis(self):
        self.user.monthly_analyses.filter(reference_month=JULY).delete()

        response = self.get()

        self.assertFalse(response.context['show_selector'])
        self.assertNotContains(response, 'name="analise"')

    def test_valid_param_shows_selected_analysis(self):
        response = self.get(analise='2026-07')

        self.assertContains(response, 'Análise de julho de 2026')
        self.assertContains(response, 'Resumo de julho.')
        self.assertNotContains(response, 'Resumo de agosto.')
        self.assertContains(response, 'Voltar para a mais recente')
        self.assertContains(response, 'value="2026-07" selected')

    def test_invalid_or_missing_param_falls_back_to_latest(self):
        for value in ('abc', '2026-13', '2026-06', '2025-01', '', '07/2026'):
            with self.subTest(analise=value):
                response = self.get(analise=value)

                self.assertContains(response, 'Resumo de agosto.')
                self.assertNotContains(
                    response, 'Voltar para a mais recente'
                )

    def test_param_of_other_user_falls_back_to_latest(self):
        for value in ('2026-09', '2026-05'):
            with self.subTest(analise=value):
                response = self.get(analise=value)

                self.assertContains(response, 'Resumo de agosto.')
                self.assertNotContains(response, 'do outro usuário')

    def test_block_never_shows_other_user_analysis(self):
        response = self.get()
        self.assertNotContains(response, 'Resumo secreto do outro usuário.')
        # September completed for the other user does not affect the
        # current month state of this user.
        self.assertEqual(response.context['current_month_state'], 'pending')
        self.assertContains(response, GENERATE_ACTION)

        self.client.force_login(self.other)
        response = self.get(analise='2026-08')

        self.assertContains(response, 'Resumo secreto do outro usuário.')
        self.assertNotContains(response, 'Resumo de agosto.')
        self.assertNotContains(response, 'Resumo de julho.')

    def test_other_dashboard_blocks_keep_current_month(self):
        response = self.get(analise='2026-07')

        self.assertEqual(response.context['month_start'], SEPTEMBER)


@override_settings(OPENAI_API_KEY='test-key', AI_ANALYSIS_ENABLED=True)
class DashboardAnalysisContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        create_analysis(cls.user, JULY)
        create_analysis(cls.user, AUGUST)

    def setUp(self):
        patcher = mock.patch(
            'django.utils.timezone.localdate', return_value=TODAY,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_at_most_three_queries(self):
        with self.assertNumQueries(3):
            context = dashboard_analysis_context(self.user, '2026-07')

        self.assertEqual(context['selected_analysis'].reference_month, JULY)
        self.assertEqual(
            context['selected_analysis'].summary,
            analysis_payload()['summary'],
        )
        self.assertFalse(context['is_latest_selected'])
        self.assertEqual(context['next_generation_date'], date(2026, 9, 30))

    @override_settings(OPENAI_API_KEY='')
    def test_no_queries_when_feature_disabled(self):
        with self.assertNumQueries(0):
            context = dashboard_analysis_context(self.user)

        self.assertFalse(context['ai_enabled'])
        self.assertIsNone(context['selected_analysis'])

    def test_one_query_when_user_disabled(self):
        self.user.profile.ai_analysis_enabled = False
        self.user.profile.save()

        with self.assertNumQueries(1):
            context = dashboard_analysis_context(self.user)

        self.assertFalse(context['ai_user_enabled'])
        self.assertEqual(context['analysis_options'], [])


GENERATE_FORM_TOKEN = re.compile(
    r'<form[^>]*action="' + re.escape(GENERATE_URL) + r'"[^>]*>\s*'
    r'<input type="hidden" name="csrfmiddlewaretoken" value="([^"]+)"'
)


@override_settings(OPENAI_API_KEY='test-key', AI_ANALYSIS_ENABLED=True)
class DashboardGenerateFormCsrfTests(TestCase):
    """Regression: the generate form must carry the CSRF token.

    ``_generate_form.html`` is included with ``only``, which drops the
    ``csrf_token`` context variable unless it is passed explicitly.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()

    def setUp(self):
        patcher = mock.patch(
            'django.utils.timezone.localdate', return_value=TODAY,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        silence_ai_logger(self)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def get_form_token(self):
        response = self.client.get(DASHBOARD_URL)
        self.assertEqual(response.status_code, 200)
        match = GENERATE_FORM_TOKEN.search(response.content.decode())
        self.assertIsNotNone(
            match, 'Form de ai:generate sem csrfmiddlewaretoken.',
        )
        return match.group(1)

    def assert_post_with_form_token_succeeds(self):
        token = self.get_form_token()
        self.assertIn(settings.CSRF_COOKIE_NAME, self.client.cookies)

        with patch_chat_model():
            response = self.client.post(
                GENERATE_URL, {'csrfmiddlewaretoken': token},
            )

        self.assertNotEqual(response.status_code, 403)
        self.assertRedirects(
            response, DASHBOARD_URL, fetch_redirect_response=False,
        )

    def test_post_without_token_is_forbidden(self):
        with patch_chat_model() as get_model:
            response = self.client.post(GENERATE_URL)

        self.assertEqual(response.status_code, 403)
        get_model.assert_not_called()

    def test_no_analysis_yet(self):
        self.assert_post_with_form_token_succeeds()

    def test_insufficient_data(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.INSUFFICIENT_DATA,
        )

        self.assert_post_with_form_token_succeeds()

    def test_failed_with_retry(self):
        create_analysis(
            self.user, SEPTEMBER, status=AnalysisStatus.FAILED, attempts=1,
        )

        self.assert_post_with_form_token_succeeds()
