# Imagem base leve do Python
FROM python:3.11-slim

# Define diretório de trabalho
WORKDIR /app

# Copia dependências primeiro para otimizar cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta exigida pelo Cloud Run
EXPOSE 8080

# Usa Gunicorn para rodar o Flask
# "app:app" significa: arquivo app.py e objeto Flask chamado app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
