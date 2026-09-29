"""On-demand analysis generation view (PRD 14.7.4)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from ai.services import GenerationOutcome, generate_monthly_analysis

OUTCOME_MESSAGES = {
    GenerationOutcome.COMPLETED: (
        messages.SUCCESS, 'Sua análise do mês está pronta.',
    ),
    GenerationOutcome.ALREADY_COMPLETED: (
        messages.INFO, 'A análise deste mês já foi gerada.',
    ),
    GenerationOutcome.IN_PROGRESS: (
        messages.INFO,
        'Sua análise já está sendo gerada. Atualize a página em instantes.',
    ),
    GenerationOutcome.INSUFFICIENT_DATA: (
        messages.WARNING,
        'Registre pelo menos 5 transações para gerar a análise.',
    ),
    GenerationOutcome.FAILED: (
        messages.ERROR,
        'Não foi possível gerar sua análise agora. Tente novamente em '
        'alguns minutos.',
    ),
    GenerationOutcome.ATTEMPTS_EXHAUSTED: (
        messages.WARNING,
        'O limite de tentativas para gerar a análise deste mês foi '
        'atingido. Você pode consultar as análises anteriores.',
    ),
    GenerationOutcome.USER_DISABLED: (
        messages.WARNING,
        'A análise com IA está desativada no seu perfil.',
    ),
    GenerationOutcome.FEATURE_DISABLED: (
        messages.ERROR,
        'A análise com IA não está disponível no momento.',
    ),
}


class GenerateAnalysisView(LoginRequiredMixin, View):
    """Generate the current month analysis of the logged-in user.

    POST only and without IDs in the URL: the service always receives
    ``request.user`` and the current month (no IDOR).
    """

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        result = generate_monthly_analysis(request.user)
        level, text = OUTCOME_MESSAGES[result.outcome]
        messages.add_message(request, level, text)
        return redirect('dashboard')
