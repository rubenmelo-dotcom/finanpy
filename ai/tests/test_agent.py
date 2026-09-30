from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ai import llm
from ai.agent import (
    AnalysisGenerationError,
    build_agent,
    run_analysis,
    sum_usage,
)
from ai.schemas import FinancialAnalysis
from ai.tests.utils import (
    fake_model,
    make_context,
    structured_response_message,
    tool_call_message,
)
from ai.tools import share_connection_with_tools
from core.test_utils import create_transaction, create_user

PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 9, 29)


class AgentFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        create_transaction(
            cls.user, amount=Decimal('250.00'), date=date(2026, 9, 10),
        )

    def setUp(self):
        self.context = make_context(self.user, PERIOD_START, PERIOD_END)

    def test_tool_calls_then_structured_output(self):
        model = fake_model(
            tool_call_message(
                'get_financial_overview',
                usage_metadata={'input_tokens': 120, 'output_tokens': 10},
            ),
            tool_call_message(
                'get_category_breakdown', {'month': '2026-09'},
                usage_metadata={'input_tokens': 200, 'output_tokens': 15},
            ),
            structured_response_message(
                usage_metadata={'input_tokens': 300, 'output_tokens': 90},
            ),
        )

        analysis, usage = run_analysis(self.context, model=model)

        self.assertIsInstance(analysis, FinancialAnalysis)
        self.assertEqual(analysis.overall_status, 'healthy')
        self.assertEqual(len(analysis.insights), 2)
        self.assertEqual(len(analysis.tips), 2)
        self.assertEqual(usage, {
            'input_tokens': 620,
            'output_tokens': 115,
            'total_tokens': 735,
        })

    def test_tools_receive_user_from_context(self):
        model = fake_model(
            tool_call_message('get_financial_overview'),
            structured_response_message(),
        )
        agent = build_agent(model)

        with share_connection_with_tools():
            result = agent.invoke(
                {'messages': [{'role': 'user', 'content': 'Analise.'}]},
                context=self.context,
            )

        tool_messages = [
            message for message in result['messages']
            if isinstance(message, ToolMessage)
            and message.name == 'get_financial_overview'
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn('"expense": "250.00"', tool_messages[0].content)

    def test_missing_structured_response_raises(self):
        model = fake_model(AIMessage(content='Texto livre, sem schema.'))

        with self.assertRaises(AnalysisGenerationError):
            run_analysis(self.context, model=model)

    def test_invalid_structured_output_is_sent_back_to_model(self):
        # ToolStrategy returns the validation error to the model, which
        # answers again with a valid payload.
        model = fake_model(
            structured_response_message(insights=[]),
            structured_response_message(),
        )

        analysis, usage = run_analysis(self.context, model=model)

        self.assertIsInstance(analysis, FinancialAnalysis)
        self.assertEqual(usage['total_tokens'], 240)


class SumUsageTests(TestCase):
    def test_sums_only_ai_messages_and_ignores_missing_metadata(self):
        messages = [
            HumanMessage(content='oi'),
            AIMessage(
                content='',
                usage_metadata={
                    'input_tokens': 10, 'output_tokens': 5,
                    'total_tokens': 15,
                },
            ),
            AIMessage(content='sem uso'),
        ]

        self.assertEqual(sum_usage(messages), {
            'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
        })


class ChatModelFactoryTests(TestCase):
    @override_settings(OPENAI_API_KEY='')
    def test_without_key_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            llm.get_chat_model()

    @override_settings(
        OPENAI_API_KEY='test-key',
        OPENAI_MODEL='modelo-teste',
        OPENAI_TIMEOUT=12.0,
        OPENAI_MAX_RETRIES=1,
    )
    def test_builds_chat_openai_from_settings(self):
        model = llm.get_chat_model()

        self.assertIsInstance(model, ChatOpenAI)
        self.assertEqual(model.model_name, 'modelo-teste')
        self.assertEqual(model.request_timeout, 12.0)
        self.assertEqual(model.max_retries, 1)

    @override_settings(OPENAI_API_KEY='')
    def test_build_agent_without_model_uses_factory(self):
        with mock.patch(
            'ai.agent.get_chat_model',
            return_value=fake_model(),
        ) as factory:
            build_agent()

        factory.assert_called_once_with()
