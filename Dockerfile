# Usa imagem base leve do Python
FROM python:3.11-slim

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos
COPY . .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expõe porta usada pelo Render
EXPOSE 5000

# Comando de inicialização (Render usa gunicorn automaticamente)
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
