from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        INCOME = 'income', 'Entrada'
        EXPENSE = 'expense', 'Saída'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name='usuário',
    )
    account = models.ForeignKey(
        'accounts.Account',
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='conta',
    )
    category = models.ForeignKey(
        'categories.Category',
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='categoria',
    )
    transaction_type = models.CharField(
        'tipo', max_length=10, choices=TransactionType.choices
    )
    description = models.CharField('descrição', max_length=255)
    amount = models.DecimalField(
        'valor',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField('data', default=timezone.localdate)
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [models.Index(fields=['user', 'date'])]
        verbose_name = 'transação'
        verbose_name_plural = 'transações'

    def __str__(self):
        return f'{self.description} - {self.amount}'

    @property
    def signed_amount(self):
        if self.transaction_type == self.TransactionType.EXPENSE:
            return -self.amount
        return self.amount
