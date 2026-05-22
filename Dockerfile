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

# Comando para rodar o Streamlit configurado para a porta do Cloud Run
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
