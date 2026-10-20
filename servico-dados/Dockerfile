FROM python:3.12-slim

# Evita buffer na saída: os logs aparecem na hora em "docker compose logs"
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copia primeiro só o requirements para aproveitar o cache de camadas do Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5001
CMD ["python", "app.py"]