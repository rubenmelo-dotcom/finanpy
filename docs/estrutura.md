# Estrutura do projeto

```text
finanpy
├── accounts/        # contas bancárias
├── categories/      # categorias de transações
├── core/            # configurações globais (settings, urls, wsgi, asgi)
├── profiles/        # perfis de usuários
├── transactions/    # transações (entradas e saídas)
├── users/           # usuários (herdando do User do Django)
├── docs/            # esta documentação
├── db.sqlite3       # banco de dados SQLite
├── manage.py
├── PRD.md           # documento de requisitos do produto
└── requirements.txt
```

## Apps

Cada domínio fica em sua própria app. Todas seguem a estrutura padrão gerada
pelo `startapp`:

```text
<app>/
├── migrations/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── tests.py
└── views.py
```

| App | Responsabilidade |
|---|---|
| `core` | Configurações globais do projeto (`settings.py`, `urls.py`) |
| `users` | Usuários do sistema |
| `profiles` | Dados de perfil do usuário |
| `accounts` | Contas bancárias do usuário |
| `categories` | Categorias de entrada e saída |
| `transactions` | Lançamentos de entradas e saídas |

## Onde colocar cada coisa

- Configurações globais: `core/settings.py`.
- Rotas globais: `core/urls.py`.
- Signals: sempre em `<app>/signals.py`, registrados no método `ready()` do
  `apps.py` da app.
- Código de um domínio fica na app desse domínio. Não crie camadas extras
  (services, repositories).

A estrutura completa prevista (templates, static, forms e urls por app) está
na seção 8.2 do [PRD](../PRD.md#82-estrutura-de-diretórios).
