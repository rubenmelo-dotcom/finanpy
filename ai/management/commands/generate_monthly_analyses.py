"""Monthly AI analysis generation (PRD 14.6.4).

Scheduled by cron for 23:59 on days 28 to 31 (``America/Sao_Paulo``):
without ``--month`` it only acts on the last day of the month. Every
generation goes through ``generate_monthly_analysis()``, so completed
analyses are never regenerated (there is no ``--force``).
"""

from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai.services import (
    GenerationOutcome,
    generate_monthly_analysis,
    is_ai_enabled,
    is_last_day_of_month,
    month_label,
    parse_month_param,
)

SUMMARY_LABELS = {
    GenerationOutcome.COMPLETED: 'Concluídas',
    GenerationOutcome.INSUFFICIENT_DATA: 'Dados insuficientes',
    GenerationOutcome.USER_DISABLED: 'Desativadas pelo usuário',
    GenerationOutcome.FAILED: 'Falhas',
    GenerationOutcome.ATTEMPTS_EXHAUSTED: 'Tentativas esgotadas',
    GenerationOutcome.IN_PROGRESS: 'Em andamento',
    GenerationOutcome.ALREADY_COMPLETED: 'Já existentes',
    GenerationOutcome.FEATURE_DISABLED: 'Indisponíveis',
}


class Command(BaseCommand):
    help = (
        'Gera a análise financeira com IA do mês para os usuários ativos. '
        'Sem --month, só age no último dia do mês (fuso '
        'America/Sao_Paulo).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            metavar='AAAA-MM',
            help=(
                'Mês já encerrado a analisar (histórico ou nova tentativa '
                'manual). O mês corrente e meses futuros são recusados.'
            ),
        )
        parser.add_argument(
            '--user',
            metavar='EMAIL',
            help='Gera apenas para o usuário ativo com este e-mail.',
        )

    def handle(self, *args, **options):
        # Computed once: a run started at 23:59 may cross midnight.
        today = timezone.localdate()
        current_month = today.replace(day=1)
        reference_month = self._reference_month(
            options['month'], current_month
        )

        if not is_ai_enabled():
            raise CommandError(
                'A análise com IA está desativada: defina OPENAI_API_KEY.'
            )

        if reference_month is None:
            if not is_last_day_of_month(today):
                self.stdout.write(
                    'Hoje não é o último dia do mês; nada a fazer.'
                )
                return
            reference_month = current_month

        users = self._users(options['user'])
        self.stdout.write(
            f'Gerando análises de {month_label(reference_month)}...'
        )
        counts = Counter()
        for user in users.iterator():
            result = generate_monthly_analysis(user, reference_month)
            counts[result.outcome] += 1
            if options['verbosity'] >= 2:
                self.stdout.write(
                    f'Usuário {user.pk}: '
                    f'{SUMMARY_LABELS[result.outcome]}'
                )
        self._write_summary(counts)

    def _reference_month(self, value, current_month):
        """Validate ``--month`` (closed months only) or return ``None``."""
        if value is None:
            return None
        reference_month = parse_month_param(value)
        if reference_month is None:
            raise CommandError(
                f'Mês inválido: "{value}". Use o formato AAAA-MM.'
            )
        if reference_month >= current_month:
            raise CommandError(
                'Informe um mês já encerrado (anterior a '
                f'{current_month:%Y-%m}); o mês corrente e meses futuros '
                'não são aceitos.'
            )
        return reference_month

    def _users(self, email):
        users = get_user_model().objects.filter(
            is_active=True
        ).order_by('pk')
        if email is None:
            return users
        users = users.filter(email=email)
        if not users.exists():
            raise CommandError(
                f'Nenhum usuário ativo com o e-mail "{email}".'
            )
        return users

    def _write_summary(self, counts):
        if not counts:
            self.stdout.write('Nenhum usuário ativo encontrado.')
            return
        summary = ' · '.join(
            f'{label}: {counts[outcome]}'
            for outcome, label in SUMMARY_LABELS.items()
            if counts[outcome]
        )
        failed = (
            counts[GenerationOutcome.FAILED]
            or counts[GenerationOutcome.FEATURE_DISABLED]
        )
        style = self.style.WARNING if failed else self.style.SUCCESS
        self.stdout.write(style(summary))
