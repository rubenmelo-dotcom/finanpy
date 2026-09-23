# Ambiente de desenvolvimento

## Pré-requisitos

- Python 3.12

## Instalação

```bash
# criar e ativar o ambiente virtual
python -m venv venv
source venv/bin/activate

# instalar as dependências
pip install -r requirements.txt
```

## Comandos

```bash
# verificar a configuração do projeto
python manage.py check

# executar o servidor de desenvolvimento
python manage.py runserver
```

O servidor fica disponível em `http://127.0.0.1:8000/`. No momento, a única
rota é `/admin/`.

## Banco de dados

O projeto usa o SQLite padrão do Django, no arquivo `db.sqlite3` da raiz.

> **Atenção:** conforme o PRD (risco R1), a model `users.User` customizada e o
> `AUTH_USER_MODEL` devem ser definidos **antes** das migrations das apps do
> projeto. Não crie migrations de domínio antes disso.

## Dependências

Novas dependências só devem ser adicionadas quando forem realmente
necessárias. Após instalar, atualize o arquivo:

```bash
pip freeze > requirements.txt
```
