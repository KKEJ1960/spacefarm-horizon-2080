"""
SpaceFarm - Simulateur de la ferme (zones de culture + réservoir d'eau + recyclage).

Principe : à chaque "tour" (toutes les 2 secondes par défaut)
  1. l'humidité de chaque zone baisse (évaporation) ;
  2. si la pompe d'une zone est ON, le réservoir baisse et l'humidité remonte ;
  3. RECYCLAGE : une partie de l'eau pompée (90 %) revient dans le réservoir ;
  4. si une fuite est simulée, le réservoir perd un litre de plus (cette eau n'est PAS recyclée) ;
  5. on publie toutes les mesures sur MQTT.

Le simulateur écoute aussi les commandes :
  spacefarm/<zone>/cmd/pompe        ->  ON ou OFF
  spacefarm/<zone>/cmd/lumiere      ->  ON ou OFF
  spacefarm/simulation/fuite        ->  ON ou OFF (fuite d'eau simulée)
  spacefarm/recyclage               ->  ON ou OFF (recyclage de l'eau, ON par défaut)
  spacefarm/simulation/reinitialiser ->  remet la ferme à zéro (au début du tour suivant) ;
                                        avec le message "DEMO", les humidités repartent des valeurs
                                        "humidite_demo_crise" de zones.json (préréglage de la démo de crise)

Les topics sont décrits dans TOPICS.md.
Lancer :  python simulateur.py
"""

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

# --- Configuration du broker (modifiable avec des variables d'environnement) ---
BROKER_HOST = os.getenv("MQTT_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Durée d'un tour de simulation (en secondes)
INTERVALLE = float(os.getenv("INTERVALLE", "2"))

# --- Constantes de la simulation ---
HUMIDITE_DEPART = float(os.getenv("HUMIDITE_DEPART", "70"))   # humidité de départ de chaque zone (%)
LUMINOSITE_ALLUMEE = (11000, 13000)   # plage de lux quand la lumière est ON
FUITE_LITRES_PAR_TOUR = 1.0           # litres perdus en plus à chaque tour quand la fuite est ON

# --- Lecture de zones.json (situé à côté de ce fichier) ---
with open(Path(__file__).parent / "zones.json", encoding="utf-8") as fichier:
    CONFIG = json.load(fichier)

# % d'humidité gagnés par litre d'eau pompé (dans zones.json : l'API en a besoin aussi)
HUMIDITE_PAR_LITRE = CONFIG["humidite_par_litre"]

# Recyclage de l'eau : part de l'eau pompée qui revient dans le réservoir à chaque tour.
# 0.90 = 90 %. La valeur est dans zones.json car l'API en a besoin pour détecter les fuites.
TAUX_RECYCLAGE = CONFIG["taux_recyclage"]
CAPACITE_RESERVOIR = CONFIG["reservoir_capacite_litres"]   # le réservoir ne dépasse jamais cette valeur

# --- État de chaque zone ---
# "pompe" et "lumiere" sont modifiés par les commandes MQTT (voir on_message).
zones = {}
for zone_id, params in CONFIG["zones"].items():
    zones[zone_id] = {
        "params": params,       # les réglages de zones.json
        "humidite": HUMIDITE_DEPART,
        "temperature": 22.0,
        "ph": 6.0,
        "pompe": False,         # pompe éteinte au départ
        "lumiere": True,        # lumière allumée au départ
    }

# État de la simulation (modifié par les commandes MQTT)
simulation = {
    "fuite": False,          # spacefarm/simulation/fuite
    "recyclage": True,       # spacefarm/recyclage : ON par défaut
    "reinitialiser": False,  # spacefarm/simulation/reinitialiser : fait au début du prochain tour
    "demo": False,           # True si la réinitialisation demandée est celle de la démo de crise
}


def borner(valeur, minimum, maximum):
    """Garde la valeur entre minimum et maximum."""
    return max(minimum, min(maximum, valeur))


def publier(client, topic, valeur, unite):
    """Publie une mesure au format {"valeur", "unite", "date"}."""
    message = {
        "valeur": valeur,
        "unite": unite,
        "date": datetime.now(timezone.utc).isoformat(),
    }
    # ensure_ascii=False : garde le "°" lisible dans le message
    client.publish(topic, json.dumps(message, ensure_ascii=False))


def on_connect(client, userdata, flags, reason_code, properties):
    """Appelée à la connexion (et à chaque reconnexion) : on s'abonne aux commandes."""
    print(f"Connecté à {BROKER_HOST}:{BROKER_PORT} - Ctrl+C pour arrêter", flush=True)
    client.subscribe("spacefarm/+/cmd/pompe")     # + = n'importe quelle zone
    client.subscribe("spacefarm/+/cmd/lumiere")
    client.subscribe("spacefarm/simulation/fuite")
    client.subscribe("spacefarm/simulation/reinitialiser")
    client.subscribe("spacefarm/recyclage")       # le broker renvoie tout de suite le dernier état connu


def on_message(client, userdata, msg):
    """Appelée à chaque commande reçue, par exemple spacefarm/zone1/cmd/pompe = ON."""
    ordre = msg.payload.decode().strip().upper()

    # Réinitialisation : on note la demande, elle est faite au début du prochain tour
    if msg.topic == "spacefarm/simulation/reinitialiser":
        simulation["demo"] = (ordre == "DEMO")   # "DEMO" = préréglage de la démo de crise
        simulation["reinitialiser"] = True
        print(f"Commande reçue : réinitialisation de la ferme{' (préréglage démo de crise)' if simulation['demo'] else ''}", flush=True)
        return

    # Commandes de simulation : fuite d'eau, recyclage de l'eau
    if msg.topic in ("spacefarm/simulation/fuite", "spacefarm/recyclage"):
        nom = "fuite" if msg.topic.endswith("/fuite") else "recyclage"
        if ordre in ("ON", "OFF"):
            simulation[nom] = (ordre == "ON")
            print(f"Commande reçue : {nom} = {ordre}", flush=True)
        else:
            print(f"Commande ignorée : {msg.topic} = {msg.payload!r}", flush=True)
        return

    # Commandes de zone
    morceaux = msg.topic.split("/")   # ["spacefarm", "zone1", "cmd", "pompe"]
    zone_id, cible = morceaux[1], morceaux[3]

    if zone_id not in zones or ordre not in ("ON", "OFF"):
        print(f"Commande ignorée : {msg.topic} = {msg.payload!r}", flush=True)
        return

    # cible vaut "pompe" ou "lumiere" : ce sont aussi les clés de l'état de la zone
    zones[zone_id][cible] = (ordre == "ON")
    print(f"Commande reçue : {zone_id} {cible} = {ordre}", flush=True)


def reinitialiser():
    """
    Remet la ferme à zéro : réservoir plein, humidités de départ, pompes éteintes, plus de fuite, recyclage actif.
    Pour la démo de crise, les humidités repartent des valeurs "humidite_demo_crise" de zones.json
    (des zones qui ont "déjà souffert") au lieu de HUMIDITE_DEPART.
    """
    for zone in zones.values():
        if simulation["demo"]:
            zone["humidite"] = float(zone["params"]["humidite_demo_crise"])
        else:
            zone["humidite"] = HUMIDITE_DEPART
        zone["temperature"] = 22.0
        zone["ph"] = 6.0
        zone["pompe"] = False
        # "lumiere" n'est pas touchée : elle est pilotée par le cycle jour/nuit de l'API
    simulation["fuite"] = False
    simulation["recyclage"] = True
    simulation["reinitialiser"] = False
    print("Ferme réinitialisée" + (" (préréglage démo de crise)" if simulation["demo"] else ""), flush=True)
    simulation["demo"] = False
    return float(CONFIG["reservoir_litres"])   # niveau de départ du réservoir


def faire_un_tour(client, reservoir):
    """Fait avancer la simulation d'un tour, publie les mesures, renvoie le niveau du réservoir."""
    eau_pompee = 0.0   # litres pompés par toutes les zones pendant ce tour

    for zone_id, zone in zones.items():
        params = zone["params"]

        # 1) Évaporation : moitié moins vite si la lumière est éteinte
        evaporation = params["evaporation"]
        if not zone["lumiere"]:
            evaporation = evaporation / 2
        zone["humidite"] -= evaporation

        # 2) Arrosage : impossible si le réservoir est vide
        if reservoir <= 0 and zone["pompe"]:
            zone["pompe"] = False
            print(f"Réservoir vide : pompe {zone_id} forcée à OFF", flush=True)
        # On lit l'état de la pompe UNE seule fois : une commande qui arrive
        # au milieu du tour ne doit pas fausser ce qu'on consomme et ce qu'on publie.
        pompe_active = zone["pompe"]
        if pompe_active:
            litres = min(params["debit_pompe"], reservoir)   # on ne pompe pas plus que ce qui reste
            reservoir -= litres
            eau_pompee += litres
            zone["humidite"] += litres * HUMIDITE_PAR_LITRE
        zone["humidite"] = borner(zone["humidite"], 0, 100)

        # 3) Température et pH : petites variations aléatoires
        zone["temperature"] = borner(zone["temperature"] + random.uniform(-0.3, 0.3), 15, 30)
        zone["ph"] = borner(zone["ph"] + random.uniform(-0.05, 0.05), 5.0, 7.5)

        # 4) Luminosité : 0 lux si la lumière est éteinte
        if zone["lumiere"]:
            luminosite = random.uniform(*LUMINOSITE_ALLUMEE)
        else:
            luminosite = 0

        # 5) Publication des mesures de la zone
        publier(client, f"spacefarm/{zone_id}/humidite", round(zone["humidite"], 2), "%")
        publier(client, f"spacefarm/{zone_id}/temperature", round(zone["temperature"], 2), "°C")
        publier(client, f"spacefarm/{zone_id}/ph", round(zone["ph"], 2), "pH")
        publier(client, f"spacefarm/{zone_id}/luminosite", round(luminosite), "lux")
        publier(client, f"spacefarm/{zone_id}/pompe", "ON" if pompe_active else "OFF", "")

        print(f"{zone_id} ({params['nom']}) : humidité {zone['humidite']:.1f} %"
              f" | pompe {'ON' if pompe_active else 'OFF'}"
              f" | lumière {'ON' if zone['lumiere'] else 'OFF'}", flush=True)

    # Recyclage : une partie de l'eau pompée revient dans le réservoir (jamais au-delà de sa capacité)
    if simulation["recyclage"]:
        reservoir = min(CAPACITE_RESERVOIR, reservoir + TAUX_RECYCLAGE * eau_pompee)

    # Fuite simulée : le réservoir perd un litre de plus, sans jamais passer sous 0.
    # Elle est retirée APRÈS le recyclage : l'eau perdue par la fuite n'est pas recyclée.
    if simulation["fuite"]:
        reservoir = max(0.0, reservoir - FUITE_LITRES_PAR_TOUR)

    # Niveau du réservoir (partagé par toutes les zones)
    publier(client, "spacefarm/reservoir/niveau", round(reservoir, 2), "L")
    print(f"réservoir : {reservoir:.2f} L"
          + (" (FUITE ACTIVE)" if simulation["fuite"] else "")
          + ("" if simulation["recyclage"] else " (recyclage coupé)"), flush=True)
    return reservoir


def main():
    # Création du client MQTT (paho-mqtt version 2 : il faut préciser la version de l'API)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT)
    client.loop_start()  # gère la connexion MQTT (et les commandes reçues) en arrière-plan

    reservoir = float(CONFIG["reservoir_litres"])   # niveau de départ en litres

    try:
        while True:
            # Une réinitialisation demandée est faite ici, au début d'un tour : jamais à moitié
            if simulation["reinitialiser"]:
                reservoir = reinitialiser()
            reservoir = faire_un_tour(client, reservoir)
            time.sleep(INTERVALLE)
    except KeyboardInterrupt:
        print("Arrêt du simulateur")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
