# CropGuard dans un conteneur Linux : sur cette machine, une politique de sécurité Windows bloque
# les .dll compilés de scikit-learn hors conteneur (voir README.md). À l'intérieur du conteneur,
# ce sont des .so Linux : la politique Windows ne s'applique pas.
#
# Construire (depuis ce dossier) :
#   docker build -t spacefarm-cropguard .
# Lancer (host.docker.internal = joindre le broker MQTT qui tourne sur le PC Windows) :
#   docker run -d --name cropguard -p 8100:8100 spacefarm-cropguard
# Arrêter :
#   docker rm -f cropguard

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Le broker MQTT tourne sur le PC hôte (conteneur mosquitto-workshop, port 1883 publié) :
# host.docker.internal le joint depuis n'importe quel conteneur, sur Docker Desktop Windows.
ENV MQTT_HOST=host.docker.internal

EXPOSE 8100

CMD ["python", "-m", "uvicorn", "cropguard:app", "--host", "0.0.0.0", "--port", "8100"]
