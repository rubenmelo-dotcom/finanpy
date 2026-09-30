"""Fake chat model and data helpers for the ``ai`` tests (PRD 14.11).

No test in ``ai/tests`` touches the network: the agent runs with
``FakeToolModel`` and every service, view and command test patches
``ai.llm.get_chat_model``.
"""

import logging
from datetime import timedelta
from itertools import count
from unittest import mock

from django.utils import timezone
from langchain.messages import AIMessage, ToolCall
from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,
)

from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.tools import AnalysisContext

_call_ids = count(1)

DEFAULT_USAGE = {'input_tokens': 100, 'output_tokens': 20}


class FakeToolModel(GenericFakeChatModel):
    """``GenericFakeChatModel`` that accepts ``bind_tools``.

    ``create_agent`` binds the tools (and the ``ToolStrategy`` schema) to
    the model; the base class does not implement ``bind_tools``, so it
    returns ``self`` and keeps answering with the scripted messages.
    """

    model_name: str = 'fake-model'

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def usage(input_tokens, output_tokens):
    """Return an ``usage_metadata`` dict."""
    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
    }


def tool_call_message(name, args=None, usage_metadata=DEFAULT_USAGE):
    """``AIMessage`` asking for one tool call."""
    return AIMessage(
        content='',
        tool_calls=[
            ToolCall(
                name=name,
                args=args or {},
                id=f'call_{next(_call_ids)}',
            )
        ],
        usage_metadata=usage(**usage_metadata),
    )


def analysis_payload(**overrides):
    """Valid ``FinancialAnalysis`` arguments (pt-BR content)."""
    payload = {
        'summary': 'Você fechou o mês com saldo positivo.',
        'overall_status': 'healthy',
        'insights': [
            {
                'title': 'Poupança em alta',
                'description': 'Sua taxa de poupança foi de 30%.',
                'kind': 'positive',
                'metric': '30%',
            },
            {
                'title': 'Alimentação concentrada',
                'description': 'Alimentação foi a maior despesa do mês.',
                'kind': 'attention',
                'metric': None,
            },
        ],
        'tips': [
            {
                'title': 'Defina um teto',
                'description': 'Limite Alimentação a R$ 600,00.',
                'priority': 'high',
                'category': 'Alimentação',
            },
            {
                'title': 'Revise assinaturas',
                'description': 'Cancele serviços pouco usados.',
                'priority': 'low',
                'category': None,
            },
        ],
    }
    payload.update(overrides)
    return payload


def structured_response_message(usage_metadata=DEFAULT_USAGE, **overrides):
    """``AIMessage`` calling the ``FinancialAnalysis`` schema tool."""
    return tool_call_message(
        'FinancialAnalysis',
        analysis_payload(**overrides),
        usage_metadata=usage_metadata,
    )


def fake_model(*messages):
    """``FakeToolModel`` that answers with ``messages`` in order."""
    return FakeToolModel(messages=iter(messages))


def default_script():
    """Overview tool call followed by the structured response."""
    return [
        tool_call_message('get_financial_overview'),
        structured_response_message(),
    ]


def patch_chat_model(model=None, **kwargs):
    """Patch ``ai.llm.get_chat_model`` (never builds ``ChatOpenAI``).

    Without ``model`` or ``side_effect``, returns a fresh scripted model
    on every call, so the mock can be reused by several generations.
    """
    if model is not None:
        kwargs['return_value'] = model
    elif 'side_effect' not in kwargs:
        kwargs['side_effect'] = lambda: fake_model(*default_script())
    return mock.patch('ai.llm.get_chat_model', **kwargs)


def silence_ai_logger(testcase):
    """Replace the console handler of the ``ai`` logger during a test.

    ``assertLogs('ai')`` keeps working (it swaps the handlers itself).
    """
    patcher = mock.patch.object(
        logging.getLogger('ai'), 'handlers', [logging.NullHandler()],
    )
    patcher.start()
    testcase.addCleanup(patcher.stop)


def make_context(user, period_start, period_end):
    return AnalysisContext(
        user_id=user.pk, period_start=period_start, period_end=period_end,
    )


def create_analysis(user, reference_month, **extra):
    """Create a ``MonthlyAnalysis`` (``COMPLETED`` with content)."""
    reference_month = reference_month.replace(day=1)
    data = {
        'period_start': reference_month,
        'period_end': reference_month,
        'status': AnalysisStatus.COMPLETED,
        'content': analysis_payload(),
        'generated_at': timezone.now(),
        'model_name': 'fake-model',
    }
    data.update(extra)
    if data['status'] != AnalysisStatus.COMPLETED and 'content' not in extra:
        data['content'] = None
    return MonthlyAnalysis.objects.create(
        user=user, reference_month=reference_month, **data
    )


def previous_month(value, months=1):
    """First day of the month ``months`` before ``value``."""
    result = value.replace(day=1)
    for _ in range(months):
        result = (result - timedelta(days=1)).replace(day=1)
    return result
