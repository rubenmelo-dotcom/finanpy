# Fluxo de trabalho

## Sprints

O desenvolvimento é dividido em sprints, cada uma com tarefas e subtarefas em
formato de checklist, na seção 13 do [PRD](../PRD.md#13-lista-de-tarefas).

- Marque `[X]` em cada subtarefa concluída.
- Uma tarefa só é marcada quando todas as suas subtarefas estiverem
  concluídas.
- Uma sprint só é encerrada quando todas as tarefas e a validação da sprint
  estiverem marcadas.

Docker e testes automatizados ficam para as sprints finais.

## Definição de pronto

Uma tarefa é considerada concluída quando:

- O código segue a PEP 8 e usa aspas simples.
- Todo o código está em inglês.
- Toda a interface está em português brasileiro.
- As telas usam somente componentes e classes do design system.
- As views privadas exigem login e isolam os dados por usuário.
- As models novas possuem `created_at` e `updated_at` e migrations geradas.
- A funcionalidade foi validada manualmente em desktop e mobile.
- Nada além do escopo solicitado foi adicionado.

## Validação antes de concluir

```bash
python manage.py check
```
