# Finanpy

Sistema web em Django para gestão de finanças pessoais: contas bancárias,
categorias, transações, um dashboard com o resumo financeiro e uma análise
mensal gerada por IA.

Stack: Python 3.12, Django 6.1, SQLite, Django Template Language,
TailwindCSS 4 (CLI standalone, sem Node.js) e LangChain com a OpenAI
(apenas para a análise com IA, opcional).

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
Compose; o `runserver` local não o carrega. As variáveis da análise com IA
(`OPENAI_*` e `LANGSMITH_TRACING`) estão na seção
[Análise financeira com IA](#análise-financeira-com-ia).

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

A suíte usa `django.test.TestCase` (um `tests.py` por app; a app `ai` usa
o pacote `ai/tests/`) e os helpers de `core/test_utils.py`. Os testes da
análise com IA usam um modelo falso e nunca acessam a rede nem precisam de
chave da OpenAI. Com o venv ativado:

```bash
python manage.py test                     # suíte completa
python manage.py test transactions        # uma app
python manage.py test ai                  # análise com IA (ai/tests/)
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

A app `ai` gera, uma vez por mês, uma análise personalizada das finanças de
cada usuário: resumo da situação, insights e dicas práticas. Um agente
LangChain (`langchain` 1.4.3 + `langchain-openai` 1.6.6) consulta os dados
do usuário por ferramentas somente leitura e devolve uma resposta
estruturada, gravada na tabela `ai_monthlyanalysis` com o histórico mês a
mês. O dashboard mostra a análise mais recente e permite selecionar as
anteriores. A especificação completa está na seção 14 do `PRD.md`.

A análise é gerada de duas formas, pelo mesmo serviço
(`ai/services.py`):

- **Automática:** comando `generate_monthly_analyses`, agendado para o
  último dia do mês às 23:59 (veja abaixo).
- **Sob demanda:** botão **Gerar análise** do dashboard (POST em
  `/analises/gerar/`), disponível em qualquer dia do mês enquanto a
  análise do mês corrente não estiver concluída.

Depois de concluída, a análise do mês fica fixa: ela nunca é regenerada
nem alterada, e o bloco do dashboard passa a ser somente de visualização.

### Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | vazio | Chave da API da OpenAI. Vazia: a análise fica desativada (o bloco some do dashboard e o comando sai com erro) e o restante do sistema funciona normalmente |
| `OPENAI_MODEL` | `gpt-6-luna` | Modelo usado pelo `ChatOpenAI` |
| `OPENAI_TIMEOUT` | `60` | Timeout, em segundos, de cada requisição à OpenAI |
| `OPENAI_MAX_RETRIES` | `2` | Novas tentativas automáticas do cliente OpenAI (rede, 429, 5xx) |
| `LANGSMITH_TRACING` | `false` | Rastreamento do LangSmith; deve ficar **desligado** para nenhum dado ser enviado a serviços externos de observabilidade |

As quatro variáveis `OPENAI_*` são lidas pelo `core/settings.py`;
`LANGSMITH_TRACING` é lida diretamente pela biblioteca `langsmith`
(dependência transitiva do LangChain), que só envia dados se ela estiver
ligada. Com Docker, preencha o `.env` (o `.env.example` já traz as cinco
variáveis). Localmente, o `runserver` não lê o `.env`: exporte a chave no
terminal antes de subir o servidor ou rodar o comando:

```bash
export OPENAI_API_KEY='sua-chave'
python manage.py runserver
```

Nunca versione a chave real: ela só pode vir do ambiente e não aparece em
logs nem nas mensagens de erro gravadas.

As regras de negócio ficam em `ai/constants.py` e não são configuráveis por
ambiente: mínimo de 5 transações no período (`AI_MIN_TRANSACTIONS`), 3
tentativas por mês (`AI_MAX_ATTEMPTS`), 3 meses anteriores analisados
(`AI_LOOKBACK_MONTHS`), geração travada considerada abandonada após 10
minutos (`AI_STALE_AFTER`) e no máximo 15 passos do agente
(`AI_RECURSION_LIMIT`).

### Comando `generate_monthly_analyses`

O comando gera a análise do mês para todos os usuários ativos com a
análise ativada no perfil. Sem `--month`, ele só age no **último dia do
mês** (data no fuso `America/Sao_Paulo`); nos outros dias, informa "Hoje
não é o último dia do mês; nada a fazer." e sai com sucesso. Por isso
basta uma linha de cron para os dias 28 a 31, às 23:59. Sem
`OPENAI_API_KEY`, o comando sai com erro.

```bash
python manage.py generate_monthly_analyses                  # último dia do mês
python manage.py generate_monthly_analyses --month 2026-09  # mês encerrado
python manage.py generate_monthly_analyses --user ana@exemplo.com
```

| Opção | Descrição |
|---|---|
| `--month AAAA-MM` | Mês já encerrado a analisar, para preencher o histórico ou repetir manualmente uma execução das 23:59 que falhou. O mês corrente e meses futuros são recusados. O período vai até o último dia desse mês |
| `--user EMAIL` | Gera apenas para o usuário ativo com esse e-mail (erro se não existir) |

As opções podem ser combinadas (`--month 2026-09 --user ana@exemplo.com`).
O mês de referência é calculado uma única vez no início da execução, então
uma execução iniciada às 23:59 que passe da meia-noite continua no mesmo
mês. Análises concluídas nunca são regeneradas (não existe `--force`);
usuários que já geraram a análise pelo botão do dashboard são ignorados.
Ao final, o comando mostra um resumo por situação (ex.:
`Concluídas: 12 · Dados insuficientes: 3 · Já existentes: 40`); com `-v 2`, mostra também o resultado de cada usuário
(pelo ID, sem e-mail). Com Docker:

```bash
docker compose exec web python manage.py generate_monthly_analyses --month 2026-09
```

### Agendamento mensal (último dia do mês, 23:59)

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
`docker compose exec` desativa o pseudo-TTY, que não existe no cron. Na
instalação local, a linha do cron precisa ter acesso à `OPENAI_API_KEY`
(defina-a no próprio crontab ou num script que a exporte).

### Custo

- **Uma análise por usuário e mês:** garantida no banco por uma
  `UniqueConstraint (usuário, mês de referência)`. Uma análise concluída
  nunca é gerada de novo, nem pelo comando nem pelo botão.
- **Sem chamada quando faltam dados:** com menos de 5 transações no
  período, a OpenAI não é chamada e a tentativa não é consumida.
- **Limite de tentativas:** no máximo 3 gerações que chamam a OpenAI por
  usuário e mês (cada uma com até `OPENAI_MAX_RETRIES` novas tentativas do
  cliente e `OPENAI_TIMEOUT` segundos por requisição). Esgotado o limite,
  o mês fica sem análise e só pode ser repetido excluindo o registro pelo
  admin.
- **Passos limitados:** cada geração tem no máximo 15 passos do agente
  (`recursion_limit`), e as ferramentas devolvem respostas pequenas (até
  10 transações por consulta).
- **Tokens registrados:** cada geração grava `input_tokens`,
  `output_tokens` e `total_tokens` (soma de todas as chamadas ao modelo),
  além do modelo usado e do número de tentativas. Consulte em **Admin →
  Análises com IA → Análises mensais** (somente leitura) ou no log do
  logger `ai`, que registra início, fim, duração e tokens de cada geração
  (sem e-mail nem valores financeiros).

### Dados enviados à OpenAI

O agente acessa apenas os dados do próprio usuário, por ferramentas
somente leitura, e só no período analisado (os 3 meses anteriores
fechados mais o mês de referência até a data da geração). São enviados:

- totais mensais de entradas, saídas, resultado, taxa de poupança e
  quantidade de transações;
- nomes das categorias, com totais e percentuais por categoria;
- nome, tipo e saldo atual das contas ativas;
- as maiores transações de um mês, até 10 por consulta: data, descrição
  (truncada em 100 caracteres), valor, categoria e conta.

**Não são enviados:** nome, e-mail, telefone, data de nascimento, IDs
internos nem dados de outros usuários. As descrições são tratadas como
dados, nunca como instruções, e o texto gerado é exibido com o autoescape
do Django.

### Como desativar

- **Por usuário:** em **Perfil → Editar perfil → Privacidade**, desmarque
  **Permitir análise com IA** (o bloco do dashboard também tem o link
  **Desativar análise com IA**). Desativada, nenhuma análise é gerada e
  nenhum dado do usuário é enviado à OpenAI, nem pelo comando nem pelo
  botão. As análises já geradas continuam guardadas e voltam a aparecer se
  a opção for reativada.
- **No sistema todo:** deixe `OPENAI_API_KEY` vazia.
