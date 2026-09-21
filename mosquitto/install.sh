#!/bin/bash
# Installe et configure Mosquitto sur la VM Debian.
# Usage : bash install.sh   (depuis le dossier mosquitto/)

# Arrêter le script à la première erreur
set -e

# Dossier où se trouve ce script (pour retrouver workshop.conf)
DOSSIER="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installation de Mosquitto (broker) et mosquitto-clients (mosquitto_pub / mosquitto_sub)"
sudo apt update
sudo apt install -y mosquitto mosquitto-clients

echo "==> Copie de la configuration du workshop"
sudo cp "$DOSSIER/workshop.conf" /etc/mosquitto/conf.d/workshop.conf

echo "==> Démarrage du service (et démarrage automatique au boot)"
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

echo "==> État du service"
systemctl is-active mosquitto

echo "Terminé. Lancez maintenant : bash test.sh"
