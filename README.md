# Finanpy

Sistema web em Django para gestão de finanças pessoais: contas bancárias,
categorias, transações e um dashboard com o resumo financeiro.

Stack: Python 3.12, Django 6.1, SQLite, Django Template Language e
TailwindCSS 4 (CLI standalone, sem Node.js).

## Requisitos

- Python 3.12+
- Linux x64 para o binário do Tailwind usado abaixo (em outros sistemas,
  baixe o binário correspondente na página de releases do Tailwind)
- Docker e Docker Compose, apenas para executar com Docker

## Instalação local

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

# 4. Banco de dados e usuário administrador
python manage.py migrate
python manage.py createsuperuser

# 5. Servidor
python manage.py runserver
```

Acesse `http://localhost:8000`. O `bin/`, o `static/css/output.css` e o
`db.sqlite3` não são versionados.

### Variáveis de ambiente

O `core/settings.py` lê as variáveis abaixo com `os.environ.get`. Sem
nenhuma delas definida, valem os padrões de desenvolvimento, e o projeto
roda localmente sem configuração extra.

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | chave `django-insecure-...` | Chave secreta do Django |
| `DEBUG` | `True` | `True`/`False` (também aceita `1`/`0`, `yes`) |
| `ALLOWED_HOSTS` | vazio | Hosts separados por vírgula |
| `SQLITE_PATH` | `db.sqlite3` na raiz | Caminho do arquivo SQLite |

O `.env.example` documenta essas variáveis. O `.env` é usado pelo Docker
Compose; o `runserver` local não o carrega.

## Desenvolvimento

Rode cada comando em um terminal separado, com o venv ativado:

```bash
# Terminal 1: recompila o CSS a cada alteração nos templates e forms
./bin/tailwindcss -i static/src/input.css -o static/css/output.css --watch

# Terminal 2: servidor de desenvolvimento
python manage.py runserver
```

O `static/src/input.css` varre `templates/` e `**/forms.py` (`@source`),
então classes usadas nos widgets dos forms também são geradas.

Build final do CSS (minificado):

```bash
./bin/tailwindcss -i static/src/input.css -o static/css/output.css --minify
```

Checagens antes de concluir uma alteração:

```bash
python manage.py check
flake8
```

## Testes

A suíte usa `django.test.TestCase` (um `tests.py` por app) e os helpers de
`core/test_utils.py`. Com o venv ativado:

```bash
python manage.py test                     # suíte completa
python manage.py test transactions        # uma app
python manage.py test accounts.tests.AccountBalanceTests  # uma classe

# Cobertura (configuração em .coveragerc)
coverage run manage.py test && coverage report
```

## Executando com Docker

A imagem é construída em dois estágios: o primeiro baixa o Tailwind CLI
standalone (x64 ou arm64, conforme a arquitetura) e gera o `output.css`
com `--minify`; o segundo, baseado em `python:3.12-slim`, instala as
dependências, copia o código e executa `collectstatic`. Ao iniciar, o
container roda `migrate` e sobe o servidor na porta 8000.

```bash
# 1. Variáveis de ambiente (o .env não é versionado)
cp .env.example .env
# edite o .env e troque a SECRET_KEY

# 2. Construir e subir
docker compose up --build
```

Acesse `http://localhost:8000`. Em outro terminal:

```bash
# Criar o usuário administrador
docker compose exec web python manage.py createsuperuser

# Rodar a suíte de testes dentro do container
docker compose exec web python manage.py test
```

Parar e subir de novo:

```bash
docker compose down
docker compose up
```

O banco SQLite fica em `/app/data/db.sqlite3` (`SQLITE_PATH`), dentro do
volume nomeado `sqlite_data`, por isso os dados persistem entre `down` e
`up`. Para apagar o banco, use `docker compose down -v` (remove o volume).

Sobre os arquivos estáticos: o container usa o `runserver` do Django com
`--insecure`, que serve os estáticos mesmo com `DEBUG=False` (padrão do
`.env.example`). É uma configuração para uso local, sem servidor de
produção (como gunicorn ou nginx), mantida assim para não adicionar
dependências ao projeto.

## Análise financeira com IA

### Agendamento mensal

O comando `generate_monthly_analyses` gera a análise do mês para todos os
usuários ativos com a análise ativada no perfil. Sem `--month`, ele só age
no **último dia do mês** (data no fuso `America/Sao_Paulo`); nos outros
dias, informa "Hoje não é o último dia do mês; nada a fazer." e sai com
sucesso. Por isso basta uma linha de cron para os dias 28 a 31, às 23:59.
Sem `OPENAI_API_KEY`, o comando sai com erro.

```bash
python manage.py generate_monthly_analyses                  # último dia do mês
python manage.py generate_monthly_analyses --month 2026-09  # mês encerrado
python manage.py generate_monthly_analyses --user ana@exemplo.com
```

`--month` aceita apenas meses já encerrados (o mês corrente e meses
futuros são recusados) e serve para preencher o histórico ou repetir
manualmente uma execução das 23:59 que falhou. Análises concluídas nunca
são regeneradas; usuários que já geraram a análise pelo botão do
dashboard são ignorados. Ao final, o comando mostra um resumo por status
(ex.: `Concluídas: 12 · Dados insuficientes: 3 · Já existentes: 40`).

O agendador precisa usar o fuso `America/Sao_Paulo` (via `CRON_TZ`, `TZ`
ou o relógio do host); caso contrário, as 23:59 do cron não coincidem com
o último dia do mês visto pela aplicação. Exemplo de `crontab -e`, com
uma linha para a instalação local e outra para o Docker (use só a que se
aplica):

```cron
CRON_TZ=America/Sao_Paulo
# Instalação local (crie antes a pasta logs/)
59 23 28-31 * * cd /caminho/finanpy && venv/bin/python manage.py generate_monthly_analyses >> logs/ai.log 2>&1
# Docker Compose (container em execução)
59 23 28-31 * * cd /caminho/finanpy && docker compose exec -T web python manage.py generate_monthly_analyses
```

`CRON_TZ` é suportado pelo cronie (Fedora, RHEL, Arch); no cron do
Debian/Ubuntu, deixe o host em `America/Sao_Paulo`
(`sudo timedatectl set-timezone America/Sao_Paulo`). O `-T` do
`docker compose exec` desativa o pseudo-TTY, que não existe no cron.
