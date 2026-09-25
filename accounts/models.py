from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from transactions.models import Transaction

INCOME = Transaction.TransactionType.INCOME
EXPENSE = Transaction.TransactionType.EXPENSE
MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO = Value(Decimal('0'), output_field=MONEY)


def _sum_by_type(lookup, transaction_type):
    return Coalesce(
        Sum(
            f'{lookup}amount',
            filter=Q(**{f'{lookup}transaction_type': transaction_type}),
        ),
        ZERO,
        output_field=MONEY,
    )


class AccountQuerySet(models.QuerySet):
    def with_balance(self, user):
        return self.filter(user=user).annotate(
            balance=ExpressionWrapper(
                F('initial_balance')
                + _sum_by_type('transactions__', INCOME)
                - _sum_by_type('transactions__', EXPENSE),
                output_field=MONEY,
            )
        )


class Account(models.Model):
    class AccountType(models.TextChoices):
        CHECKING = 'checking', 'Conta corrente'
        SAVINGS = 'savings', 'Poupança'
        WALLET = 'wallet', 'Carteira'
        INVESTMENT = 'investment', 'Investimento'
        OTHER = 'other', 'Outro'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='accounts',
        verbose_name='usuário',
    )
    name = models.CharField('nome', max_length=100)
    bank_name = models.CharField(
        'banco/instituição', max_length=100, blank=True
    )
    account_type = models.CharField(
        'tipo',
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.CHECKING,
    )
    initial_balance = models.DecimalField(
        'saldo inicial',
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    is_active = models.BooleanField('ativa', default=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    objects = AccountQuerySet.as_manager()

    class Meta:
        ordering = ['name']
        verbose_name = 'conta'
        verbose_name_plural = 'contas'

    def __str__(self):
        return self.name

    def current_balance(self):
        totals = self.transactions.aggregate(
            income=_sum_by_type('', INCOME),
            expense=_sum_by_type('', EXPENSE),
        )
        return (
            self.initial_balance + totals['income'] - totals['expense']
        )
