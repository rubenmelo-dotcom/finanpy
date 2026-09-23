# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Finanpy é um monolito Django full stack de gestão de finanças pessoais
(contas bancárias, categorias, transações e dashboard). O projeto está no
início da Sprint 1: apps criadas e registradas, mas sem models, views, URLs,
templates ou estáticos — a única rota é `/admin/`.

- **`PRD.md` é a fonte da verdade** para requisitos, rotas (seção 8.4), models
  (8.5), design system (9) e a lista de tarefas por sprint (13). Consulte a
  seção relevante antes de implementar qualquer coisa.
- `docs/` resume o PRD e descreve o estado atual do projeto.
- Ao concluir subtarefas, marque `[X]` na seção 13 do PRD. Uma tarefa só é
  marcada quando todas as subtarefas estiverem concluídas.

## Comandos

```bash
source venv/bin/activate             # o venv fica em ./venv (o PRD cita .venv)
pip install -r requirements.txt
python manage.py check               # validação obrigatória antes de concluir
python manage.py runserver
python manage.py makemigrations && python manage.py migrate
```

Previstos no PRD, ainda não configurados:

```bash
flake8                               # PEP 8; .flake8 com max-line-length = 79
./bin/tailwindcss -i static/src/input.css -o static/css/output.css --watch
python manage.py test                # sprint 10 (django.test.TestCase)
python manage.py test accounts.tests.AccountTests.test_name  # teste único
coverage run manage.py test && coverage report
```

Tailwind usa o **CLI standalone** (binário em `bin/`, não versionado) — sem
Node.js. Rode o `--watch` e o `runserver` em terminais separados.

## Armadilha crítica: model de usuário customizada (risco R1)

`users.User` deve herdar de `AbstractUser` com `username = None`,
`email` único, `USERNAME_FIELD = 'email'` e um `UserManager` em
`users/managers.py`; `AUTH_USER_MODEL = 'users.User'` precisa estar definido
**antes da primeira migration de qualquer app do projeto**.

O `db.sqlite3` atual **já teve as migrations nativas aplicadas** (`auth`,
`admin`, `sessions`) com o `User` padrão. Ao introduzir `AUTH_USER_MODEL`, o
banco precisa ser apagado e recriado, senão o histórico de migrations fica
inconsistente. Não gere migrations de domínio antes disso.

## Arquitetura

- **Uma app por domínio:** `users`, `profiles`, `accounts`, `categories`,
  `transactions`. `core` guarda settings/URLs globais e, conforme o PRD,
  `core/views.py` terá `HomeView` (site público) e `DashboardView`, por não
  pertencerem a um domínio.
- **Sem camadas extras** (services, repositories). Lógica fica em models,
  forms e views da própria app.
- **Isolamento por usuário:** toda model de domínio tem FK para `User`. Views
  privadas usam `LoginRequiredMixin`, filtram `get_queryset()` por
  `self.request.user` (ID de outro usuário → 404) e atribuem o usuário em
  `form_valid()`. Querysets de FK nos forms (conta, categoria) também são
  filtrados pelo usuário.
- **Saldo calculado, nunca armazenado:** `Account.current_balance()` =
  `initial_balance + entradas − saídas`, via agregação do ORM. Não crie
  signals para atualizar saldo.
- **`Transaction.account` e `Transaction.category` usam `PROTECT`:** as
  `DeleteView` de conta/categoria tratam `ProtectedError` com mensagem
  amigável.
- **`Profile` é criado por signal** `post_save` de `User` em
  `profiles/signals.py`. Signals sempre em `<app>/signals.py`, registrados no
  `ready()` do `apps.py`.
- `category.category_type == transaction_type` é validado no `clean()` do
  form de transação.
- **Frontend:** DTL + TailwindCSS 4, sem frameworks JS. Templates em
  `templates/` na raiz com `base.html` → `layouts/{public,auth,app}.html` e
  componentes reutilizáveis em `templates/components/_*.html`. Tokens de cor
  ficam em `static/src/input.css` (`@theme`), cujos `@source` varrem
  `templates` e `**/forms.py` — classes Tailwind usadas em widgets de forms
  só são geradas por causa disso. Toda tela deve usar apenas os componentes e
  classes da seção 9 do PRD.
- URLs públicas em português (`/contas/`, `/transacoes/nova/`), com
  namespaces por app (`accounts:list`, `transactions:create`...).

## Padrões obrigatórios

- Código em **inglês**; tudo que aparece na interface em **pt-BR** (inclusive
  `verbose_name`, labels e mensagens).
- PEP 8, linhas ≤ 79 caracteres, **aspas simples**.
- Toda model tem `created_at` (`auto_now_add=True`) e `updated_at`
  (`auto_now=True`).
- Valores monetários: `DecimalField(max_digits=12, decimal_places=2)`, nunca
  `float`.
- Preferir recursos nativos do Django: CBVs genéricas, `LoginView`,
  `LogoutView` (logout via POST), `PasswordChangeView`, `ModelForm`,
  `messages`, `admin`.
- Evitar N+1 com `select_related`, `aggregate` e `annotate`.
- Nada além do escopo pedido; não adicionar dependências sem necessidade
  (depois de instalar, `pip freeze > requirements.txt`).
- Docker e testes automatizados só nas sprints finais (10 e 11).

## Divergências entre PRD e projeto atual

| PRD | Projeto |
|---|---|
| Django 5.x | Django 6.1.1 (`requirements.txt`) |
| `db.sqlite` | `db.sqlite3` |
| `.venv/` | `venv/` |
| `LANGUAGE_CODE = 'pt-br'`, `America/Sao_Paulo` | ainda `en-us` / `UTC` |

O repositório Git tem raiz em `/home/ruben/pycodebr` (diretório pai), não em
`finanpy/`; ainda não existem `.gitignore`, `.flake8` nem `README.md` aqui.
