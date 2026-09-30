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
| Frontend | Django Template Language + TailwindCSS 4 (CLI standalone, sem Node.js) |
| Autenticação | Nativa do Django, com login por e-mail |
| Testes | `django.test` (`TestCase`) + `coverage` |
| Container | Docker + Docker Compose |
| IA | LangChain `1.4.3` + `langchain-openai` `1.6.6`, modelo OpenAI configurável (`OPENAI_MODEL`, padrão `gpt-6-luna`) |

## Estado atual

As sprints 1 a 12 do PRD estão implementadas; na sprint 12 resta a
validação (tarefa 12.14).

- Site público, cadastro e login por e-mail, perfil, contas bancárias,
  categorias, transações e dashboard com o resumo financeiro do mês.
- Suíte de testes automatizados em todas as apps e execução via Docker
  Compose.
- **Análise financeira com IA** (app `ai`, seção 14 do [PRD](../PRD.md)):
  um agente especialista gera, uma vez por mês, uma análise por usuário
  (resumo, insights e dicas), gravada no model `MonthlyAnalysis`. A geração
  é feita pelo comando `generate_monthly_analyses`, agendado para o último
  dia do mês às 23:59, ou pelo botão **Gerar análise** do dashboard. O
  dashboard mostra a análise mais recente e permite selecionar as
  anteriores.
- O usuário pode desativar a análise com IA no perfil
  (`Profile.ai_analysis_enabled`); desativada, nenhum dado dele é enviado à
  OpenAI. Sem `OPENAI_API_KEY`, a funcionalidade fica desligada e o resto do
  sistema funciona normalmente.

Instruções de instalação, variáveis de ambiente, agendamento e custos da
análise com IA estão no [README](../README.md).
