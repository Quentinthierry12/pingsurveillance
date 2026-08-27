FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
# Toute la config vient de l'image (pas de volume sur /app/config, voir
# docker-compose.yml) : committe ton vrai config/services.yaml dans le repo
# pour qu'il soit inclus ici, puis redéploie.
COPY config/ ./config/

RUN mkdir -p /app/data

EXPOSE 8085

CMD ["python3", "src/main.py"]
