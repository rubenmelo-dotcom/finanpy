# Estrutura do projeto

```text
finanpy
├── accounts/        # contas bancárias
├── ai/              # análise financeira mensal com IA
├── categories/      # categorias de transações
├── core/            # configurações globais, HomeView e DashboardView
├── profiles/        # perfis de usuários
├── transactions/    # transações (entradas e saídas)
├── users/           # usuários (herdando do User do Django)
├── templates/       # templates DTL (layouts, componentes e telas por app)
├── static/          # input.css do Tailwind e CSS gerado
├── docs/            # esta documentação
├── db.sqlite3       # banco de dados SQLite (não versionado)
├── Dockerfile
├── docker-compose.yml
├── .env.example     # variáveis de ambiente documentadas
├── manage.py
├── PRD.md           # documento de requisitos do produto
└── requirements.txt
```

## Apps

Cada domínio fica em sua própria app. As apps de domínio seguem a estrutura
padrão:

```text
<app>/
├── migrations/
├── __init__.py
├── admin.py
├── apps.py
├── forms.py
├── models.py
├── tests.py
├── urls.py
└── views.py
```

| App | Responsabilidade |
|---|---|
| `core` | Configurações globais (`settings.py`, `urls.py`), `HomeView` e `DashboardView` |
| `users` | Usuários do sistema (login por e-mail) |
| `profiles` | Dados de perfil do usuário e a preferência `ai_analysis_enabled` |
| `accounts` | Contas bancárias do usuário |
| `categories` | Categorias de entrada e saída |
| `transactions` | Lançamentos de entradas e saídas |
| `ai` | Análise financeira mensal com IA (model `MonthlyAnalysis`, agente, comando e geração sob demanda) |

### App `ai`

É a única app com módulos além de models, forms e views (exceção prevista
no RNF27 do PRD), porque a integração com o LLM não cabe nessas camadas:

```text
ai/
├── management/commands/generate_monthly_analyses.py  # comando agendado
├── migrations/
├── tests/           # utils.py (modelo falso) e test_*.py por camada
├── admin.py         # admin somente leitura de MonthlyAnalysis
├── agent.py         # build_agent() e run_analysis()
├── constants.py     # AI_MIN_TRANSACTIONS, AI_MAX_ATTEMPTS etc.
├── llm.py           # get_chat_model(): única fábrica do ChatOpenAI
├── models.py        # AnalysisStatus e MonthlyAnalysis
├── prompts.py       # SYSTEM_PROMPT e mensagem do usuário
├── schemas.py       # FinancialAnalysis (Pydantic) e SCHEMA_VERSION
├── services.py      # generate_monthly_analysis() e contexto do dashboard
├── tools.py         # AnalysisContext e tools somente leitura
├── urls.py          # /analises/gerar/
└── views.py         # GenerateAnalysisView (POST)
```

Os templates do bloco do dashboard ficam em `templates/ai/`
(`_analysis_card.html` e `_generate_form.html`).

## Onde colocar cada coisa

- Configurações globais: `core/settings.py`.
- Rotas globais: `core/urls.py`.
- Signals: sempre em `<app>/signals.py`, registrados no método `ready()` do
  `apps.py` da app.
- Código de um domínio fica na app desse domínio. Não crie camadas extras
  (services, repositories); a app `ai` é a única exceção.

A estrutura completa (templates, static e arquivos por app) está na seção
8.2 do [PRD](../PRD.md#82-estrutura-de-diretórios).
