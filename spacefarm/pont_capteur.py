"""
SpaceFarm - Pont capteurs réels -> MQTT.

Deux vrais capteurs (reliés à un ESP32) sont branchés en USB sur ce PC : une sonde d'humidité du
sol, et un capteur de température/humidité de l'air. Le Wi-Fi de l'ESP32 ne fonctionne pas ici
(problème d'alimentation du port USB-C) : les mesures arrivent donc par le câble série (port COM),
pas directement par MQTT.

Ce pont fait le lien : il lit les lignes envoyées par l'ESP32 sur le port série, en alternance :
    HUM;<valeur_brute>;<pourcentage>          exemple : HUM;306;25.8
    AIR;<temperature>;<humidite_air>          exemple : AIR;25.8;52
(la calibration est faite côté ESP32) et republie sur MQTT, sur des topics SÉPARÉS de ceux du
simulateur :
    spacefarm/<zone>/humidite_reelle
    spacefarm/<zone>/temperature_reelle
On ne publie pas directement sur spacefarm/<zone>/humidite ou .../temperature : le simulateur y
publie aussi en boucle, les deux se marcheraient dessus. C'est l'API (voir api.py) qui choisit sa
source et détecte l'absence de mesures réelles (retour au mode simulé au bout de 15 s sans
message). L'humidité de l'air (deuxième valeur des lignes AIR) est lue, mais n'est pour l'instant
ni publiée ni utilisée : aucune zone de zones.json ne modélise cette mesure.

Lancer (depuis le dossier spacefarm) :  python pont_capteur.py
Arrêter : Ctrl+C
"""

import json
import os
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import serial   # pyserial (voir requirements.txt)

# --- Constantes (modifiables avec des variables d'environnement, comme le reste du projet) ---
PORT_SERIE = os.getenv("PORT_SERIE", "COM3")           # port COM de l'ESP32
VITESSE_SERIE = int(os.getenv("VITESSE_SERIE", "115200"))   # doit correspondre au Serial.begin() de l'ESP32
ZONE_CIBLE = os.getenv("ZONE_CIBLE", "zone1")           # zone dont ces capteurs remplacent les mesures simulées

BROKER_HOST = os.getenv("MQTT_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

TOPIC_HUMIDITE = f"spacefarm/{ZONE_CIBLE}/humidite_reelle"
TOPIC_TEMPERATURE = f"spacefarm/{ZONE_CIBLE}/temperature_reelle"


def publier(client, topic, valeur, unite, brut=None):
    """Publie une mesure du capteur réel : format habituel {"valeur", "unite", "date"}, plus "source"
    (et "brut", la valeur brute du capteur, seulement quand elle existe : c'est le cas pour l'humidité,
    pas pour la température, déjà calibrée par l'ESP32)."""
    message = {
        "valeur": valeur,
        "unite": unite,
        "date": datetime.now(timezone.utc).isoformat(),
        "source": "capteur-reel",
    }
    if brut is not None:
        message["brut"] = brut
    client.publish(topic, json.dumps(message, ensure_ascii=False))


def lire_ligne(ligne, client):
    """Interprète une ligne reçue de l'ESP32 (HUM;<brut>;<pourcentage> ou AIR;<temp>;<humidite_air>)
    et publie la mesure correspondante si elle est valide."""
    morceaux = ligne.split(";")
    type_ligne = morceaux[0] if morceaux else ""

    if type_ligne == "HUM":
        if len(morceaux) != 3:
            print(f"Ligne ignorée (format inattendu) : {ligne!r}", flush=True)
            return
        try:
            brut = int(morceaux[1])
            pourcentage = float(morceaux[2])
        except ValueError:
            print(f"Ligne ignorée (valeurs illisibles) : {ligne!r}", flush=True)
            return
        publier(client, TOPIC_HUMIDITE, pourcentage, "%", brut=brut)
        print(f"{ZONE_CIBLE} : humidité réelle {pourcentage:.1f} % (brut {brut})", flush=True)

    elif type_ligne == "AIR":
        if len(morceaux) != 3:
            print(f"Ligne ignorée (format inattendu) : {ligne!r}", flush=True)
            return
        try:
            temperature = float(morceaux[1])
            humidite_air = float(morceaux[2])   # lue mais non utilisée (voir docstring du fichier)
        except ValueError:
            print(f"Ligne ignorée (valeurs illisibles) : {ligne!r}", flush=True)
            return
        publier(client, TOPIC_TEMPERATURE, temperature, "°C")
        print(f"{ZONE_CIBLE} : température réelle {temperature:.1f} °C "
              f"(humidité de l'air {humidite_air:.0f} %, non utilisée)", flush=True)

    elif ligne:   # une ligne vide arrive simplement quand rien n'a été reçu avant le délai d'attente
        print(f"Ligne ignorée (format inattendu) : {ligne!r}", flush=True)


def ouvrir_port_serie():
    """Ouvre le port série. En cas d'échec, message clair puis arrêt du programme."""
    try:
        return serial.Serial(PORT_SERIE, VITESSE_SERIE, timeout=1)
    except serial.SerialException as erreur:
        print(f"Impossible d'ouvrir le port {PORT_SERIE} : {erreur}", flush=True)
        print(
            f"Vérifiez que l'ESP32 est bien branché sur {PORT_SERIE}, et qu'AUCUN autre programme "
            "ne l'utilise en même temps (par exemple le « Moniteur série » de l'IDE Arduino : "
            "il faut le fermer avant de lancer ce pont).",
            flush=True,
        )
        sys.exit(1)


def main():
    port = ouvrir_port_serie()
    print(f"Port série {PORT_SERIE} ouvert à {VITESSE_SERIE} bauds - zone cible : {ZONE_CIBLE}", flush=True)

    # Client MQTT (paho-mqtt version 2 : il faut préciser la version de l'API, comme dans les autres scripts)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT)
    client.loop_start()   # gère la connexion MQTT en arrière-plan
    print(f"Connecté à {BROKER_HOST}:{BROKER_PORT} - publie sur {TOPIC_HUMIDITE} et {TOPIC_TEMPERATURE} "
          "- Ctrl+C pour arrêter", flush=True)

    try:
        while True:
            ligne = port.readline().decode(errors="ignore").strip()
            lire_ligne(ligne, client)
    except KeyboardInterrupt:
        print("Arrêt du pont capteur", flush=True)
    except serial.SerialException as erreur:
        # Par exemple l'ESP32 débranché en cours de route : on s'arrête proprement.
        # L'API, elle, détectera l'absence de mesures au bout de 15 s et repassera la zone en simulé.
        print(f"Le port série a été perdu (ESP32 débranché ?) : {erreur}", flush=True)
    finally:
        port.close()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
