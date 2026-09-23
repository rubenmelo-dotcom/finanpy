# Padrões de código

Regras definidas no [PRD](../PRD.md#7-requisitos-não-funcionais) que valem
para todo código do projeto.

## Estilo

- Seguir a **PEP 8**, com linhas de até 79 caracteres.
- Usar **aspas simples** sempre que possível.
- Código simples e legível. Não adicionar nada além do que foi solicitado.

```python
# correto
name = models.CharField('Nome', max_length=100)

# evitar
name = models.CharField("Nome", max_length=100)
```

## Idioma

| Onde | Idioma |
|---|---|
| Código (nomes de variáveis, funções, classes, models, campos) | Inglês |
| Interface (textos, `verbose_name`, labels, mensagens de erro e sucesso) | Português brasileiro |

## Recursos nativos do Django

Prefira sempre o que o Django já oferece:

- Class Based Views genéricas (`TemplateView`, `ListView`, `CreateView`,
  `UpdateView`, `DeleteView`).
- Views de autenticação nativas (`LoginView`, `LogoutView`,
  `PasswordChangeView`).
- `ModelForm`, framework `messages`, `admin` e ORM.

## Models

- Toda model deve ter os campos de auditoria:

```python
created_at = models.DateTimeField(auto_now_add=True)
updated_at = models.DateTimeField(auto_now=True)
```

- Valores monetários usam `DecimalField(max_digits=12, decimal_places=2)`,
  nunca `float`.
- Use `select_related` e agregações do ORM para evitar consultas N+1.

## Signals

- Ficam obrigatoriamente em `signals.py` dentro da app correspondente.
- São registrados no método `ready()` do `apps.py` da app.

## Segurança e isolamento de dados

- Views privadas usam `LoginRequiredMixin`.
- Querysets sempre filtrados por `request.user`. Um usuário nunca acessa dados
  de outro (ID de outro usuário retorna 404).
- CSRF ativo e logout via POST.
- Validadores de senha nativos do Django.

## Banco de dados

- Somente o SQLite padrão do Django.

## Frontend

- Django Template Language + TailwindCSS, sem frameworks JavaScript.
- Todas as telas devem seguir o mesmo design system, descrito na seção 9 do
  [PRD](../PRD.md#9-design-system).
