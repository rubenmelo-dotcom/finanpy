"""Agent construction and execution (PRD 14.5.2).

The agent has no memory between runs (no checkpointer): each generation
only uses the data returned by the read-only tools. The user and the
period reach the tools exclusively through ``AnalysisContext``.
"""

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import AIMessage

from ai.constants import AI_RECURSION_LIMIT
from ai.llm import get_chat_model
from ai.prompts import SYSTEM_PROMPT, build_user_message
from ai.schemas import FinancialAnalysis
from ai.tools import (
    ANALYSIS_TOOLS,
    AnalysisContext,
    share_connection_with_tools,
)

USAGE_KEYS = ('input_tokens', 'output_tokens', 'total_tokens')


class AnalysisGenerationError(Exception):
    """The agent finished without a valid structured analysis."""


def build_agent(model=None):
    """Build the financial analyst agent.

    ``model`` allows injecting a fake chat model in tests; by default the
    ``ChatOpenAI`` from ``get_chat_model()`` is used (which raises
    ``ImproperlyConfigured`` without an API key).
    """
    return create_agent(
        model or get_chat_model(),
        tools=ANALYSIS_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        context_schema=AnalysisContext,
        response_format=ToolStrategy(FinancialAnalysis),
    )


def sum_usage(messages):
    """Sum ``usage_metadata`` of every ``AIMessage`` in ``messages``."""
    usage = dict.fromkeys(USAGE_KEYS, 0)
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        metadata = message.usage_metadata or {}
        for key in USAGE_KEYS:
            usage[key] += metadata.get(key) or 0
    return usage


def run_analysis(context, model=None):
    """Run the agent for ``context`` and return ``(analysis, usage)``.

    ``analysis`` is a validated ``FinancialAnalysis`` and ``usage`` a dict
    with ``input_tokens``, ``output_tokens`` and ``total_tokens`` summed
    over all model calls. OpenAI errors and ``GraphRecursionError`` are
    propagated to the caller (the service); a missing structured response
    raises ``AnalysisGenerationError``.
    """
    agent = build_agent(model)
    message = build_user_message(
        context.period_start,
        context.period_end,
        context.period_end.replace(day=1),
    )
    with share_connection_with_tools():
        result = agent.invoke(
            {'messages': [{'role': 'user', 'content': message}]},
            context=context,
            config={'recursion_limit': AI_RECURSION_LIMIT},
        )
    usage = sum_usage(result.get('messages', []))
    analysis = result.get('structured_response')
    if not isinstance(analysis, FinancialAnalysis):
        raise AnalysisGenerationError(
            'The agent finished without a structured response.'
        )
    return analysis, usage
