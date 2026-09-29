"""ChatOpenAI factory built from settings (PRD 14.5.2).

This is the only place where ``ChatOpenAI`` is instantiated. The API key,
model name, timeout and retries come exclusively from ``settings``, which
reads them from the environment.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_openai import ChatOpenAI


def get_chat_model():
    """Return the configured ``ChatOpenAI`` chat model.

    Raises ``ImproperlyConfigured`` when ``OPENAI_API_KEY`` is empty, so
    the OpenAI API is never called without a key. Instantiating the model
    does not perform any network request.
    """
    if not settings.OPENAI_API_KEY:
        raise ImproperlyConfigured(
            'OPENAI_API_KEY is not set; the AI analysis is disabled.'
        )
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
