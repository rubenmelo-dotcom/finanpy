# Visão geral

O **Finanpy** é uma aplicação web de gestão de finanças pessoais, construída
como um monolito Django full stack.

## Princípios

- **Simples e enxuto:** sem over engineering e sem nada além do que foi
  solicitado.
- **Recursos nativos do Django** sempre que possível.
- **Domínios isolados** em apps Django separadas.

## Stack

| Item | Definição |
|---|---|
| Linguagem | Python 3.12 |
| Framework | Django 6.1.1 (ver `requirements.txt`) |
| Banco de dados | SQLite padrão do Django |
| Frontend (previsto no PRD) | Django Template Language + TailwindCSS |
| Autenticação (prevista no PRD) | Nativa do Django, com login por e-mail |

## Estado atual

O projeto está na fase inicial de setup (Sprint 1 do PRD):

- Projeto Django criado com o módulo de configuração `core`.
- Apps `users`, `profiles`, `accounts`, `categories` e `transactions` criadas
  e registradas em `INSTALLED_APPS`, ainda sem models, views ou URLs.
- A única rota existente é `/admin/`.
- `core/settings.py` ainda está com os valores gerados pelo Django
  (`LANGUAGE_CODE = 'en-us'`, `TIME_ZONE = 'UTC'`). O PRD define `pt-br` e
  `America/Sao_Paulo`.

As funcionalidades do sistema (cadastro, contas, categorias, transações e
dashboard) estão descritas no [PRD](../PRD.md), mas **ainda não foram
implementadas**.
