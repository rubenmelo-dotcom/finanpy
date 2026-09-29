"""Monthly generation service and dashboard context (PRD 14.6 and 14.7).

``generate_monthly_analysis()`` is the only code path that writes
``MonthlyAnalysis`` rows and calls the agent; the management command and
the dashboard button both go through it. The agent always runs outside
``transaction.atomic()`` (SQLite would block writes during the whole LLM
call); concurrency is handled by the ``UniqueConstraint`` plus a
conditional ``UPDATE`` that reserves the row (PRD 14.6.3).

Logs (logger ``ai``) carry only the user ID, month, status, duration,
attempts and tokens: never e-mail, financial values or descriptions.
"""

import calendar
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import openai
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from langchain.agents.structured_output import StructuredOutputError
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from ai import llm
from ai.agent import AnalysisGenerationError, run_analysis
from ai.constants import (
    AI_LOOKBACK_MONTHS,
    AI_MAX_ATTEMPTS,
    AI_MIN_TRANSACTIONS,
    AI_STALE_AFTER,
)
from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.schemas import SCHEMA_VERSION
from ai.tools import AnalysisContext
from profiles.models import Profile
from transactions.models import Transaction

logger = logging.getLogger('ai')

MAX_ERROR_MESSAGE_LENGTH = 500
MONTH_PARAM_PATTERN = re.compile(r'^(\d{4})-(\d{2})$')
API_KEY_PATTERN = re.compile(r'sk-[A-Za-z0-9_*-]{4,}')
MONTH_NAMES = (
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
    'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
)

# Configuration problems: logged with ``logger.error``.
CONFIGURATION_ERRORS = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
)
# Transient or expected failures: logged with ``logger.warning``.
# ``openai.OpenAIError`` covers timeout, connection, rate limit and 5xx
# (after the client's own ``max_retries``).
EXPECTED_ERRORS = (
    openai.OpenAIError,
    GraphRecursionError,
    AnalysisGenerationError,
    StructuredOutputError,
    ValidationError,
)


class GenerationOutcome(StrEnum):
    """What ``generate_monthly_analysis()`` did (for view and command)."""

    COMPLETED = 'completed'
    ALREADY_COMPLETED = 'already_completed'
    IN_PROGRESS = 'in_progress'
    INSUFFICIENT_DATA = 'insufficient_data'
    FAILED = 'failed'
    ATTEMPTS_EXHAUSTED = 'attempts_exhausted'
    USER_DISABLED = 'user_disabled'
    FEATURE_DISABLED = 'feature_disabled'


@dataclass(frozen=True)
class GenerationResult:
    """Result of a generation request.

    ``analysis`` is ``None`` when no record was created or read (analysis
    disabled by the user or by the system, or unexpected error before the
    record existed).
    """

    outcome: GenerationOutcome
    analysis: MonthlyAnalysis | None = None


# Month and period helpers (PRD 14.6.2)

def is_ai_enabled():
    """Return whether the AI analysis is available (API key configured).

    ``settings.AI_ANALYSIS_ENABLED`` mirrors ``bool(OPENAI_API_KEY)``; the
    key itself is checked so that ``override_settings(OPENAI_API_KEY=...)``
    in tests is enough to toggle the feature.
    """
    return bool(settings.OPENAI_API_KEY)


def current_reference_month():
    """Return the first day of the current month (``America/Sao_Paulo``)."""
    return timezone.localdate().replace(day=1)


def month_end(value):
    """Return the last day of the month of ``value``."""
    last_day = calendar.monthrange(value.year, value.month)[1]
    return value.replace(day=last_day)


def is_last_day_of_month(day):
    """Return whether ``day`` is the last day of its month."""
    return day == month_end(day)


def add_months(value, months):
    """Return the first day of the month ``months`` away from ``value``."""
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_label(value):
    """Return the month in pt-BR, e.g. ``'outubro de 2026'``."""
    return f'{MONTH_NAMES[value.month - 1]} de {value.year}'


def analysis_period(reference_month, generated_on):
    """Return ``(period_start, period_end)`` for a reference month.

    The period goes from the first day of ``AI_LOOKBACK_MONTHS`` months
    before the reference month to the generation date, clipped to the
    last day of the reference month (closed months, via ``--month``).
    """
    reference_month = reference_month.replace(day=1)
    if generated_on < reference_month:
        raise ValueError('The reference month is in the future.')
    period_start = add_months(reference_month, -AI_LOOKBACK_MONTHS)
    period_end = min(generated_on, month_end(reference_month))
    return period_start, period_end


# Generation (PRD 14.6.3)

def _user_allows_ai(user):
    """Read ``Profile.ai_analysis_enabled`` from the database.

    A missing profile counts as disabled (nothing is sent to OpenAI).
    """
    enabled = (
        Profile.objects.filter(user=user)
        .values_list('ai_analysis_enabled', flat=True)
        .first()
    )
    return enabled is True


def _get_or_create_analysis(user, reference_month, period_start, period_end):
    defaults = {'period_start': period_start, 'period_end': period_end}
    try:
        with transaction.atomic():
            analysis, _ = MonthlyAnalysis.objects.get_or_create(
                user=user, reference_month=reference_month,
                defaults=defaults,
            )
    except IntegrityError:
        # Another process created the row at the same time.
        analysis = MonthlyAnalysis.objects.get(
            user=user, reference_month=reference_month
        )
    return analysis


def _claim(analysis, period_start, period_end, now):
    """Reserve the row with a single conditional ``UPDATE``."""
    claimable = (
        Q(status__in=[
            AnalysisStatus.PENDING, AnalysisStatus.INSUFFICIENT_DATA,
        ])
        | Q(status=AnalysisStatus.FAILED, attempts__lt=AI_MAX_ATTEMPTS)
        | Q(
            status=AnalysisStatus.PROCESSING,
            started_at__lt=now - AI_STALE_AFTER,
        )
    )
    return MonthlyAnalysis.objects.filter(pk=analysis.pk).filter(
        claimable
    ).update(
        status=AnalysisStatus.PROCESSING,
        started_at=now,
        period_start=period_start,
        period_end=period_end,
        updated_at=now,
    )


def _unclaimed_outcome(analysis):
    if analysis.status == AnalysisStatus.COMPLETED:
        return GenerationOutcome.ALREADY_COMPLETED
    if analysis.status == AnalysisStatus.FAILED:
        return GenerationOutcome.ATTEMPTS_EXHAUSTED
    return GenerationOutcome.IN_PROGRESS


def _finish(analysis, claimed_at, **fields):
    """Write the final state, only if this process still owns the row.

    A generation slower than ``AI_STALE_AFTER`` may have been taken over
    by another process; in that case this process does not overwrite it.
    """
    fields['updated_at'] = timezone.now()
    updated = MonthlyAnalysis.objects.filter(
        pk=analysis.pk,
        status=AnalysisStatus.PROCESSING,
        started_at=claimed_at,
    ).update(**fields)
    analysis.refresh_from_db()
    return updated == 1


def _sanitize(text):
    """Remove the API key (or anything like one) from ``text``."""
    key = settings.OPENAI_API_KEY
    if key:
        text = text.replace(key, '***')
    return API_KEY_PATTERN.sub('sk-***', text)


def _validation_detail(exc):
    """Describe a pydantic error without the input values."""
    return '; '.join(
        '{}: {}'.format(
            '.'.join(str(part) for part in error['loc']), error['msg']
        )
        for error in exc.errors(include_input=False, include_url=False)
    )


def error_message(exc):
    """Internal ``error_message``: exception class + truncated message.

    Never contains the API key, the prompt or the data sent (pydantic
    errors are described without the invalid input).
    """
    if isinstance(exc, ValidationError):
        detail = _validation_detail(exc)
    elif isinstance(exc, StructuredOutputError):
        source = getattr(exc, 'source', None)
        detail = (
            _validation_detail(source)
            if isinstance(source, ValidationError)
            else type(source).__name__ if source else ''
        )
    else:
        detail = str(exc)
    detail = _sanitize(detail)[:MAX_ERROR_MESSAGE_LENGTH]
    return f'{type(exc).__name__}: {detail}'


def _log_failure(exc, user_id, month):
    name = type(exc).__name__
    if isinstance(exc, CONFIGURATION_ERRORS):
        logger.error(
            'AI analysis configuration error user_id=%s month=%s '
            'error=%s', user_id, month, name,
        )
    elif isinstance(exc, EXPECTED_ERRORS):
        logger.warning(
            'AI analysis failed user_id=%s month=%s error=%s',
            user_id, month, name,
        )
    else:
        logger.exception(
            'AI analysis unexpected error user_id=%s month=%s error=%s',
            user_id, month, name,
        )


def _log_finish(analysis, outcome, started, usage=None):
    usage = usage or {}
    logger.info(
        'AI analysis finished user_id=%s month=%s status=%s outcome=%s '
        'duration=%.2fs attempts=%s input_tokens=%s output_tokens=%s '
        'total_tokens=%s',
        analysis.user_id, f'{analysis.reference_month:%Y-%m}',
        analysis.status, outcome, time.monotonic() - started,
        analysis.attempts, usage.get('input_tokens'),
        usage.get('output_tokens'), usage.get('total_tokens'),
    )


def _process_claimed(user, analysis, started_at, started):
    """Run steps 5 to 9 of PRD 14.6.3 on a reserved row."""
    month = f'{analysis.reference_month:%Y-%m}'
    transaction_count = Transaction.objects.filter(
        user=user,
        date__gte=analysis.period_start,
        date__lte=analysis.period_end,
    ).count()
    if transaction_count < AI_MIN_TRANSACTIONS:
        # No LLM call: the attempt is not consumed.
        _finish(
            analysis, started_at,
            status=AnalysisStatus.INSUFFICIENT_DATA, error_message='',
        )
        outcome = GenerationOutcome.INSUFFICIENT_DATA
        _log_finish(analysis, outcome, started)
        return GenerationResult(outcome, analysis)

    # The user may have disabled the analysis meanwhile (LGPD).
    if not _user_allows_ai(user):
        _finish(
            analysis, started_at,
            status=AnalysisStatus.PENDING, started_at=None,
        )
        outcome = GenerationOutcome.USER_DISABLED
        _log_finish(analysis, outcome, started)
        return GenerationResult(outcome, analysis)

    try:
        # Resolved through the module so tests can patch
        # ``ai.llm.get_chat_model``.
        model = llm.get_chat_model()
    except ImproperlyConfigured:
        _finish(
            analysis, started_at,
            status=AnalysisStatus.PENDING, started_at=None,
        )
        logger.error(
            'AI analysis not configured user_id=%s month=%s',
            analysis.user_id, month,
        )
        return GenerationResult(GenerationOutcome.FEATURE_DISABLED)

    MonthlyAnalysis.objects.filter(pk=analysis.pk).update(
        attempts=F('attempts') + 1, updated_at=timezone.now(),
    )
    context = AnalysisContext(
        user_id=user.pk,
        period_start=analysis.period_start,
        period_end=analysis.period_end,
    )
    try:
        # Outside any transaction: never wrap this call in atomic().
        result, usage = run_analysis(context, model=model)
    except Exception as exc:
        _log_failure(exc, analysis.user_id, month)
        _finish(
            analysis, started_at,
            status=AnalysisStatus.FAILED, error_message=error_message(exc),
        )
        outcome = GenerationOutcome.FAILED
        _log_finish(analysis, outcome, started)
        return GenerationResult(outcome, analysis)

    model_name = getattr(model, 'model_name', None) or settings.OPENAI_MODEL
    owned = _finish(
        analysis, started_at,
        status=AnalysisStatus.COMPLETED,
        content=result.model_dump(mode='json'),
        schema_version=SCHEMA_VERSION,
        model_name=str(model_name)[:100],
        input_tokens=usage.get('input_tokens'),
        output_tokens=usage.get('output_tokens'),
        total_tokens=usage.get('total_tokens'),
        generated_at=timezone.now(),
        error_message='',
    )
    if not owned:
        logger.warning(
            'AI analysis result discarded (row taken over) user_id=%s '
            'month=%s', analysis.user_id, month,
        )
        outcome = _unclaimed_outcome(analysis)
    else:
        outcome = GenerationOutcome.COMPLETED
    _log_finish(analysis, outcome, started, usage)
    return GenerationResult(outcome, analysis)


def _generate(user, reference_month, today):
    month = f'{reference_month:%Y-%m}'
    if not _user_allows_ai(user):
        logger.info(
            'AI analysis skipped user_id=%s month=%s outcome=%s',
            user.pk, month, GenerationOutcome.USER_DISABLED,
        )
        return GenerationResult(GenerationOutcome.USER_DISABLED)

    period_start, period_end = analysis_period(reference_month, today)
    analysis = _get_or_create_analysis(
        user, reference_month, period_start, period_end
    )
    if analysis.status == AnalysisStatus.COMPLETED:
        return GenerationResult(
            GenerationOutcome.ALREADY_COMPLETED, analysis
        )

    started_at = timezone.now()
    if not _claim(analysis, period_start, period_end, started_at):
        analysis.refresh_from_db()
        outcome = _unclaimed_outcome(analysis)
        logger.info(
            'AI analysis skipped user_id=%s month=%s outcome=%s',
            user.pk, month, outcome,
        )
        return GenerationResult(outcome, analysis)

    analysis.refresh_from_db()
    started = time.monotonic()
    logger.info(
        'AI analysis started user_id=%s month=%s attempts=%s',
        user.pk, month, analysis.attempts,
    )
    try:
        return _process_claimed(user, analysis, started_at, started)
    except Exception as exc:
        # Database or other unexpected error after the reservation.
        _log_failure(exc, user.pk, month)
        _finish(
            analysis, started_at,
            status=AnalysisStatus.FAILED, error_message=error_message(exc),
        )
        return GenerationResult(GenerationOutcome.FAILED, analysis)


def generate_monthly_analysis(user, reference_month=None):
    """Generate the analysis of ``user`` for ``reference_month``.

    ``reference_month`` defaults to the current month; any day of the
    month is normalised to day 1. Closed months use the last day of the
    month as the end of the period. Returns a ``GenerationResult`` and
    never raises (errors are recorded as ``FAILED`` and logged), except
    ``ValueError`` for a reference month in the future.
    """
    if not is_ai_enabled():
        return GenerationResult(GenerationOutcome.FEATURE_DISABLED)
    today = timezone.localdate()
    reference_month = (reference_month or today).replace(day=1)
    if reference_month > today:
        raise ValueError('The reference month is in the future.')
    try:
        return _generate(user, reference_month, today)
    except Exception as exc:
        _log_failure(exc, user.pk, f'{reference_month:%Y-%m}')
        return GenerationResult(GenerationOutcome.FAILED)


# Dashboard context (PRD 14.7)

def parse_month_param(value):
    """Parse ``YYYY-MM`` into the first day of the month, or ``None``."""
    match = MONTH_PARAM_PATTERN.match((value or '').strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return None


def current_month_state(analysis, now=None):
    """State of the current month for the dashboard block (PRD 14.7.3).

    One of ``pending`` (no record, ``PENDING`` or expired ``PROCESSING``),
    ``processing``, ``completed``, ``insufficient_data``, ``failed``
    (retry allowed) or ``failed_final`` (attempts exhausted).
    """
    if analysis is None or analysis.status == AnalysisStatus.PENDING:
        return 'pending'
    if analysis.status == AnalysisStatus.PROCESSING:
        now = now or timezone.now()
        stale = (
            analysis.started_at is None
            or analysis.started_at < now - AI_STALE_AFTER
        )
        return 'pending' if stale else 'processing'
    if analysis.status == AnalysisStatus.FAILED:
        return 'failed' if analysis.can_retry else 'failed_final'
    return analysis.status


def dashboard_analysis_context(user, month_param=None):
    """Context of the analysis block and selector (PRD 14.7.1–14.7.3).

    At most 3 queries: the profile preference, the completed analyses
    plus the current month record (without ``content``) and the
    ``content`` of the selected analysis. ``month_param`` (``?analise=``)
    invalid, without a completed analysis or from another user falls back
    to the most recent one; every query is filtered by ``user``.
    """
    today = timezone.localdate()
    current_month = today.replace(day=1)
    context = {
        'ai_enabled': is_ai_enabled(),
        'ai_user_enabled': False,
        'ai_min_transactions': AI_MIN_TRANSACTIONS,
        'current_month': current_month,
        'current_month_label': month_label(current_month),
        'next_generation_date': month_end(today),
        'current_month_analysis': None,
        'current_month_state': 'pending',
        'can_generate': False,
        'selected_analysis': None,
        'selected_month_label': '',
        'latest_analysis': None,
        'is_latest_selected': True,
        'analysis_options': [],
        'show_selector': False,
    }
    if not context['ai_enabled']:
        return context
    context['ai_user_enabled'] = _user_allows_ai(user)
    if not context['ai_user_enabled']:
        return context

    rows = list(
        MonthlyAnalysis.objects.for_user(user)
        .filter(
            Q(status=AnalysisStatus.COMPLETED)
            | Q(reference_month=current_month)
        )
        .defer('content')
        .order_by('-reference_month')
    )
    completed = [
        row for row in rows if row.status == AnalysisStatus.COMPLETED
    ]
    current = next(
        (row for row in rows if row.reference_month == current_month),
        None,
    )
    state = current_month_state(current)

    latest = completed[0] if completed else None
    requested = parse_month_param(month_param)
    selected = next(
        (row for row in completed if row.reference_month == requested),
        latest,
    )
    if selected is not None:
        selected.refresh_from_db(fields=['content'])

    context.update({
        'current_month_analysis': current,
        'current_month_state': state,
        'can_generate': state in ('pending', 'insufficient_data', 'failed'),
        'selected_analysis': selected,
        'selected_month_label': (
            month_label(selected.reference_month) if selected else ''
        ),
        'latest_analysis': latest,
        'is_latest_selected': selected is latest,
        'analysis_options': [
            {
                'value': f'{row.reference_month:%Y-%m}',
                'label': month_label(row.reference_month),
                'is_latest': row is latest,
                'is_selected': row is selected,
            }
            for row in completed
        ],
        'show_selector': len(completed) >= 2,
    })
    return context
