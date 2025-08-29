FROM python:3.11-slim

WORKDIR /src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

# Porta exposta para a aplicação
EXPOSE 7860

# Comando padrão ao iniciar o container
CMD ["python", "src/main.py"]
