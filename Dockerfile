# syntax=docker/dockerfile:1

# Estágio 1: gera o output.css com o Tailwind CLI standalone (sem Node.js).
FROM python:3.12-slim AS tailwind

ARG TARGETARCH
ARG TAILWIND_URL=https://github.com/tailwindlabs/tailwindcss/releases/latest/download

WORKDIR /build

RUN case "$TARGETARCH" in arm64) arch=arm64 ;; *) arch=x64 ;; esac \
    && python -c "import sys, urllib.request; \
urllib.request.urlretrieve(sys.argv[1], '/usr/local/bin/tailwindcss')" \
    "$TAILWIND_URL/tailwindcss-linux-$arch" \
    && chmod +x /usr/local/bin/tailwindcss

# Os @source do input.css varrem templates/ e **/forms.py.
COPY . .
RUN tailwindcss -i static/src/input.css -o static/css/output.css --minify

# Estágio 2: imagem final da aplicação.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SQLITE_PATH=/app/data/db.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=tailwind /build/static/css/output.css static/css/output.css
RUN python manage.py collectstatic --noinput

# Usuário sem privilégios; /app/data recebe o volume do SQLite.
RUN useradd --create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data
USER app

EXPOSE 8000

# runserver não serve estáticos com DEBUG=False; --insecure força isso
# (uso local, sem servidor de produção). Ver README.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec python manage.py runserver 0.0.0.0:8000 --insecure"]
