# Dockerfile
FROM python:3.11-slim

# Evita prompts interativos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências do sistema necessárias para psycopg2 (se usar psycopg2-binary às vezes não é necessário,
# mas deixamos pacotes básicos para segurança)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
 && rm -rf /var/lib/apt/lists/*

# Copia arquivos de requirements primeiro (cache layer)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . .

# Cria diretório de logs
RUN mkdir -p /var/log/db_controller && chown -R 1000:1000 /var/log/db_controller

# Expõe porta (Render usa $PORT)
EXPOSE 5000

# Comando de inicialização recomendado para Render (Gunicorn)
# Render define a variável $PORT automaticamente, mas deixamos fallback
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4"]
