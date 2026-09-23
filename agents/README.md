# Agentes de IA do Finanpy

Time de agentes especialistas na stack do projeto (Python 3.12, Django 6.1,
Django Template Language, TailwindCSS 4 via CLI standalone, SQLite). Todos
seguem o [PRD](../PRD.md) como fonte da verdade e os padrões do
[CLAUDE.md](../CLAUDE.md).

## Índice

| Agente | Função | Quando usar |
|---|---|---|
| [`django-backend`](django-backend.md) | Backend Django | Models, migrations, `UserManager`, ModelForms, CBVs, URLs, admin, signals, `settings.py`, saldo, isolamento por usuário. Sprints 1, 3–8. |
| [`django-templates`](django-templates.md) | Frontend DTL | `base.html`, layouts, componentes `_*.html`, telas de cada app, forms renderizados, messages, paginação, formatação de moeda/data, JS inline do menu. Sprints 2–9. |
| [`tailwindcss`](tailwindcss.md) | Estilo / design system | Tailwind CLI standalone em `bin/`, `input.css` (`@theme`, `@source`, classes de componente), build do `output.css`, classes não geradas, consistência visual. Sprints 1, 2 e 9. |
| [`qa-playwright`](qa-playwright.md) | QA / tester | Validar no navegador (Playwright MCP) fluxos, isolamento, mensagens, responsividade, acessibilidade e fidelidade ao design system. Ao fim de cada tela, correção ou sprint. |
| [`django-tests`](django-tests.md) | Testes automatizados | Suíte com `django.test.TestCase` e `coverage` (Sprint 10) e diagnóstico de testes falhando. |
| [`devops-docker`](devops-docker.md) | DevOps | Variáveis de ambiente, Dockerfile, Docker Compose, `.dockerignore`, `.env.example` (Sprint 11). |

## Fluxo típico de uma funcionalidade

```text
django-backend ──► django-templates ──► tailwindcss ──► qa-playwright
   (models,           (telas e             (classes        (valida no
    forms, views)      componentes)         faltantes)       navegador)
        ▲                                                       │
        └──────────── bugs reportados, com agente indicado ─────┘
```

- Setup e design system (sprints 1–2): `tailwindcss` + `django-templates`,
  com `django-backend` no `settings.py`.
- CRUDs (sprints 3–8): `django-backend` → `django-templates` → `qa-playwright`.
- Refinamentos (sprint 9): `qa-playwright` levanta os problemas; os demais
  corrigem.
- Sprints finais: `django-tests` (10) e `devops-docker` (11).

## MCP servers utilizados

| MCP | Agentes | Para quê |
|---|---|---|
| **context7** | `django-backend`, `django-templates`, `tailwindcss`, `django-tests`, `devops-docker` | Consultar a documentação atual antes de escrever código. IDs: Django 6.1 `/websites/djangoproject_en_6_1`, Tailwind `/tailwindlabs/tailwindcss.com`, Docker `/docker/docs`, Compose `/docker/compose`. |
| **playwright** | `qa-playwright` | Navegar, interagir, redimensionar e tirar screenshots do sistema rodando em `http://127.0.0.1:8000`. Configurado em [`../.mcp.json`](../.mcp.json). |

O Playwright MCP precisa de Node.js (`npx`) só para o próprio servidor MCP; o
projeto continua sem Node. Na primeira execução o agente instala o Chromium
(`browser_install`), ou rode antes:
`npx playwright install chromium` (no WSL, as bibliotecas do sistema podem
exigir `sudo npx playwright install-deps chromium`).

## Como usar no Claude Code

O Claude Code carrega subagentes de `.claude/agents/`. Para ativar estes
agentes sem duplicar os arquivos:

```bash
mkdir -p .claude && ln -s ../agents .claude/agents
```

Depois, peça explicitamente, por exemplo: "use o agente django-backend para
implementar a tarefa 5.1 do PRD" ou "rode o qa-playwright na sprint 5".

## Regras comuns a todos os agentes

- Ler a seção relevante do PRD antes de agir e marcar `[X]` na seção 13 ao
  concluir subtarefas (exceto o `qa-playwright`, que só reporta).
- Código em inglês, interface em pt-BR, PEP 8, ≤ 79 colunas, aspas simples.
- Nada além do escopo pedido; sem dependências desnecessárias.
- `python manage.py check` antes de concluir.
