from decimal import Decimal

from django.conf import settings
from django.db import models


class AccountQuerySet(models.QuerySet):
    def with_balance(self, user):
        # Sprint 7 (task 7.3): annotate initial_balance + Sum('amount',
        # filter=income) - Sum('amount', filter=expense) over
        # 'transactions', using Coalesce for empty sums.
        return self.filter(user=user).annotate(
            balance=models.F('initial_balance')
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
        # Sprint 7 (task 7.3): aggregate Sum('amount') of income and
        # expense over self.transactions with Coalesce and return
        # initial_balance + income - expense.
        return self.initial_balance
