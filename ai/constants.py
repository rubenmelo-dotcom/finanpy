"""Business rule constants for the AI analysis (PRD 14.8).

Kept in their own module to avoid circular imports between ``models.py``,
``agent.py`` and ``services.py``. Not configurable by environment.
"""

from datetime import timedelta

# Minimum number of transactions in the analysed period to call the LLM.
AI_MIN_TRANSACTIONS = 5

# Attempts that call the LLM per user and reference month.
AI_MAX_ATTEMPTS = 3

# Closed months analysed before the reference month.
AI_LOOKBACK_MONTHS = 3

# A generation in ``PROCESSING`` older than this can be taken over.
AI_STALE_AFTER = timedelta(minutes=10)

# Max steps of the agent graph per generation (``recursion_limit``).
AI_RECURSION_LIMIT = 15
