# Finanpy

Sistema web em Django para gestão de finanças pessoais: contas bancárias,
categorias, transações e um dashboard com o resumo financeiro.

## Requisitos

- Python 3.12+
- Linux x64 (para outros sistemas, baixe o binário do Tailwind
  correspondente)

## Instalação

```bash
# 1. Ambiente virtual e dependências
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Tailwind CLI standalone (v4, sem Node.js)
mkdir -p bin
curl -sLo bin/tailwindcss \
  https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x bin/tailwindcss

# 3. Gerar o CSS
./bin/tailwindcss -i static/src/input.css -o static/css/output.css

# 4. Banco de dados
python manage.py migrate

# 5. Servidor
python manage.py runserver
```

> O `migrate` inicial só deve ser executado a partir da sprint 3, depois da
> criação da model `users.User` (`AUTH_USER_MODEL`).

## Desenvolvimento

Rode cada comando em um terminal separado, com o venv ativado:

```bash
# Terminal 1: recompila o CSS a cada alteração nos templates e forms
./bin/tailwindcss -i static/src/input.css -o static/css/output.css --watch

# Terminal 2: servidor de desenvolvimento
python manage.py runserver
```

Checagens antes de concluir uma alteração:

```bash
python manage.py check
flake8
```

## Build final do CSS

```bash
./bin/tailwindcss -i static/src/input.css -o static/css/output.css --minify
```
