"""Pydantic schemas for the structured output (PRD 14.5.5).

The agent returns ``FinancialAnalysis`` through
``ToolStrategy(FinancialAnalysis)``. The descriptions below are read by
the model, so they stay in pt-BR, like the generated content. Any change
in the format must increment ``SCHEMA_VERSION``.
"""

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class Insight(BaseModel):
    """Observação sobre as finanças do usuário no período analisado."""

    title: str = Field(
        max_length=80,
        description='Título curto do insight, em pt-BR',
    )
    description: str = Field(
        max_length=300,
        description=(
            'Explicação do insight em pt-BR, citando os números '
            'retornados pelas ferramentas'
        ),
    )
    kind: Literal['positive', 'attention', 'neutral'] = Field(
        description=(
            'Natureza do insight: positive (ponto positivo), '
            'attention (ponto de atenção) ou neutral (informativo)'
        ),
    )
    metric: str | None = Field(
        default=None,
        max_length=40,
        description='Valor de destaque, ex.: "R$ 1.234,56" ou "+18%"',
    )


class Tip(BaseModel):
    """Recomendação prática para o usuário."""

    title: str = Field(
        max_length=80,
        description='Título curto da dica, em pt-BR',
    )
    description: str = Field(
        max_length=300,
        description='Ação concreta e prática recomendada, em pt-BR',
    )
    priority: Literal['high', 'medium', 'low'] = Field(
        description='Prioridade da dica: high, medium ou low',
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description='Nome da categoria relacionada, se houver',
    )


class FinancialAnalysis(BaseModel):
    """Análise financeira mensal de um usuário."""

    summary: str = Field(
        max_length=600,
        description='Resumo geral da situação financeira, em pt-BR',
    )
    overall_status: Literal['healthy', 'attention', 'critical'] = Field(
        description=(
            'Situação geral: healthy (saudável), attention (atenção) '
            'ou critical (crítica)'
        ),
    )
    insights: list[Insight] = Field(
        min_length=2,
        max_length=5,
        description='De 2 a 5 insights sobre o período analisado',
    )
    tips: list[Tip] = Field(
        min_length=2,
        max_length=5,
        description='De 2 a 5 dicas práticas, da mais para a menos '
                    'prioritária',
    )
