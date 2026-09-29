"""MonthlyAnalysis model (PRD 14.4)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from ai.constants import AI_MAX_ATTEMPTS


class AnalysisStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    PROCESSING = 'processing', 'Gerando'
    COMPLETED = 'completed', 'Concluída'
    FAILED = 'failed', 'Falhou'
    INSUFFICIENT_DATA = 'insufficient_data', 'Dados insuficientes'


class MonthlyAnalysisQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def completed(self):
        return self.filter(status=AnalysisStatus.COMPLETED)

    def latest_completed(self, user):
        return self.for_user(user).completed().order_by(
            '-reference_month'
        ).first()


class MonthlyAnalysis(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monthly_analyses',
        verbose_name='usuário',
    )
    reference_month = models.DateField('mês de referência')
    period_start = models.DateField('início do período')
    period_end = models.DateField('fim do período')
    status = models.CharField(
        'situação',
        max_length=20,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
    )
    content = models.JSONField('conteúdo', null=True, blank=True)
    schema_version = models.PositiveSmallIntegerField(
        'versão do schema', default=1
    )
    model_name = models.CharField('modelo', max_length=100, blank=True)
    input_tokens = models.PositiveIntegerField(
        'tokens de entrada', null=True, blank=True
    )
    output_tokens = models.PositiveIntegerField(
        'tokens de saída', null=True, blank=True
    )
    total_tokens = models.PositiveIntegerField(
        'total de tokens', null=True, blank=True
    )
    attempts = models.PositiveSmallIntegerField('tentativas', default=0)
    error_message = models.TextField('mensagem de erro', blank=True)
    started_at = models.DateTimeField('iniciada em', null=True, blank=True)
    generated_at = models.DateTimeField(
        'gerada em', null=True, blank=True
    )
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    objects = MonthlyAnalysisQuerySet.as_manager()

    class Meta:
        ordering = ['-reference_month']
        verbose_name = 'análise mensal'
        verbose_name_plural = 'análises mensais'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'reference_month'],
                name='unique_analysis_per_user_month',
            ),
            models.CheckConstraint(
                condition=Q(reference_month__day=1),
                name='analysis_reference_month_first_day',
            ),
        ]

    def __str__(self):
        return f'{self.user} · {self.reference_month:%m/%Y}'

    @property
    def is_final(self):
        return self.status == AnalysisStatus.COMPLETED

    @property
    def can_retry(self):
        return (
            self.status == AnalysisStatus.FAILED
            and self.attempts < AI_MAX_ATTEMPTS
        )

    def _content_value(self, key, default):
        if not isinstance(self.content, dict):
            return default
        value = self.content.get(key)
        return default if value is None else value

    @property
    def summary(self):
        return self._content_value('summary', '')

    @property
    def overall_status(self):
        return self._content_value('overall_status', '')

    @property
    def insights(self):
        return self._content_value('insights', [])

    @property
    def tips(self):
        return self._content_value('tips', [])
