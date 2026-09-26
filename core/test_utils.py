"""Simple helpers to create domain objects in tests."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Account
from categories.models import Category
from transactions.models import Transaction

DEFAULT_PASSWORD = 'SenhaForte!2026'


def create_user(email='user@example.com', password=DEFAULT_PASSWORD,
                **extra):
    """Create a regular user (Profile is created by signal)."""
    return get_user_model().objects.create_user(
        email=email, password=password, **extra
    )


def create_account(user, **extra):
    """Create an active checking account for ``user``."""
    data = {
        'name': 'Conta Principal',
        'bank_name': 'Banco Teste',
        'account_type': Account.AccountType.CHECKING,
        'initial_balance': Decimal('1000.00'),
        'is_active': True,
    }
    data.update(extra)
    return Account.objects.create(user=user, **data)


def create_category(user, **extra):
    """Create an expense category for ``user``."""
    data = {
        'name': 'Alimentação',
        'category_type': Category.CategoryType.EXPENSE,
        'color': '#8B5CF6',
    }
    data.update(extra)
    return Category.objects.create(user=user, **data)


def create_transaction(user, account=None, category=None, **extra):
    """Create a transaction for ``user``.

    Missing account/category are created for the same user. The
    ``transaction_type`` defaults to the category type so both match.
    """
    if account is None:
        account = create_account(user)
    if category is None:
        category = create_category(
            user,
            category_type=extra.get(
                'transaction_type', Category.CategoryType.EXPENSE
            ),
        )
    data = {
        'transaction_type': category.category_type,
        'description': 'Transação de teste',
        'amount': Decimal('100.00'),
        'date': timezone.localdate(),
    }
    data.update(extra)
    return Transaction.objects.create(
        user=user, account=account, category=category, **data
    )
