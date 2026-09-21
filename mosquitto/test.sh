#!/bin/bash
# Teste le broker Mosquitto avec mosquitto_sub et mosquitto_pub.
# Usage : bash test.sh   (sur la VM, après install.sh)

TOPIC="test/horizon2080"
MESSAGE="bonjour horizon 2080"

# On teste via l'adresse IP de la VM (pas localhost) :
# cela prouve que le broker écoute bien sur 0.0.0.0 et pas seulement en local.
IP=$(hostname -I | awk '{print $1}')
FICHIER=$(mktemp)

echo "1) Le port 1883 est-il ouvert sur 0.0.0.0 ?"
ss -ltn | grep ':1883'

echo
echo "2) Abonnement à '$TOPIC' via $IP (attend 1 message, 5 s max)"
mosquitto_sub -h "$IP" -t "$TOPIC" -C 1 -W 5 > "$FICHIER" &
PID_SUB=$!
sleep 1   # laisse le temps à l'abonné de se connecter avant de publier

echo "3) Publication de : $MESSAGE"
mosquitto_pub -h "$IP" -t "$TOPIC" -m "$MESSAGE"

wait $PID_SUB   # attend la fin de mosquitto_sub

echo
echo "4) Message reçu par l'abonné :"
cat "$FICHIER"

if [ "$(cat "$FICHIER")" = "$MESSAGE" ]; then
    echo "OK : le broker fonctionne."
else
    echo "ÉCHEC : message non reçu (voir journal : sudo journalctl -u mosquitto -n 20)"
fi
rm -f "$FICHIER"
