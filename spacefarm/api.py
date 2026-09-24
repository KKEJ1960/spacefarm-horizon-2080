"""
SpaceFarm - API + moteur de règles + WaterLoop (suivi de l'eau, alertes) + mode crise.

Ce service est séparé du simulateur. Il fait cinq choses :
  1. il écoute tous les topics "spacefarm/#" et garde en mémoire le DERNIER état
     de chaque zone et du réservoir ;
  2. il applique des règles et envoie des commandes au simulateur :
       - arrosage : pompe ON sous "seuil_arrosage", OFF au-dessus de "seuil_arrosage + 15"
       - priorité de l'eau : réservoir bas -> zones non vitales coupées, une seule pompe vitale à la fois
       - lumière  : cycle jour/nuit accéléré (2 min de jour, 1 min de nuit)
  3. il surveille l'eau : litres consommés par zone, alertes (survie, réservoir bas, fuite),
     publiées sur "spacefarm/alertes" ;
  3bis. CAPTEURS RÉELS (pont_capteur.py) : la zone ZONE_CAPTEUR_REEL (zone1 par défaut) peut recevoir
     son humidité et sa température de vrais capteurs, sur "spacefarm/<zone>/humidite_reelle" et
     "spacefarm/<zone>/temperature_reelle", au lieu du simulateur. Le reste (pH, luminosité, pompe)
     reste simulé. Sans mesure réelle depuis DELAI_CAPTEUR_REEL secondes, la mesure concernée
     repasse automatiquement en simulé (indépendamment pour l'humidité et la température) ;
  4. MODE CRISE (contamination du recyclage) : le recyclage de l'eau est COUPÉ, budget d'eau
     limité, zones non vitales sacrifiées, zones vitales maintenues juste au-dessus du seuil de
     survie, éclairage réduit. La crise se termine toute seule au bout de DUREE_CRISE_SECONDES
     (le recyclage est alors rétabli) ;
  4bis. RÉACTIONS ANTICIPÉES (module ajouté par un membre de l'équipe) : arrosage un peu avancé
     quand il fait chaud (température ≥ SEUIL_TEMP_CHALEUR), et quand CropGuard (service séparé,
     voir cropguard/) signale une plante en souffrance sur "cropguard/<zone>/sante" ;
  5. il expose tout ça par HTTP pour le dashboard React.

Routes : GET /etat, GET /alertes, POST /simulation/fuite?etat=ON|OFF,
         GET /crise, POST /crise/activer, POST /crise/desactiver,
         POST /reinitialiser (remet la ferme à zéro, pour préparer la démo),
         POST /preparer-demo-crise (réinitialisation avec des humidités proches des seuils de survie)

Lancer (depuis le dossier spacefarm) :
    python -m uvicorn api:app --port 8000
Puis ouvrir http://127.0.0.1:8000/etat  (ou http://127.0.0.1:8000/docs)
"""

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration du broker (modifiable avec des variables d'environnement) ---
BROKER_HOST = os.getenv("MQTT_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Durée d'un tour du simulateur (en secondes) : DOIT être la même valeur que côté simulateur
INTERVALLE = float(os.getenv("INTERVALLE", "2"))

# --- Règles en fonctionnement normal ---
MARGE_ARRET_POMPE = 15          # la pompe s'arrête quand humidité > seuil_arrosage + 15
DUREE_JOUR = 120                # secondes de "jour" (lumière ON)
DUREE_NUIT = 60                 # secondes de "nuit" (lumière OFF)
SEUIL_RESERVOIR_BAS = 30        # % de la capacité : sous ce seuil -> alerte "attention" + priorité de l'eau
SEUIL_RESERVOIR_CRITIQUE = 10   # % de la capacité : sous ce seuil -> alerte "critique"
TOLERANCE_FUITE = 0.5           # litres : baisse du réservoir tolérée au-delà de ce que les pompes expliquent
MAX_ALERTES = 200               # on garde les 200 dernières alertes en mémoire

# --- Capteurs réels (pont_capteur.py) ---
ZONE_CAPTEUR_REEL = os.getenv("ZONE_CAPTEUR_REEL", "zone1")   # zone dont l'humidité et la température peuvent venir de vrais capteurs
DELAI_CAPTEUR_REEL = 15         # secondes sans message d'un capteur réel avant de repasser sa mesure en simulée

# --- Réaction à la température (chaleur) : ajouté par un membre de l'équipe ---
SEUIL_TEMP_CHALEUR = float(os.getenv("SEUIL_TEMP_CHALEUR", "28"))   # au-delà : alerte + arrosage anticipé
BONUS_ARROSAGE_CHALEUR = 8      # quand il fait chaud, on arrose sous seuil_arrosage + ce bonus

# --- Liaison CropGuard -> SpaceFarm (santé des plantes, voir cropguard/) ---
SEUIL_SANTE_ATTENTION = float(os.getenv("SEUIL_SANTE_ATTENTION", "60"))  # santé sous ce % : plante fragilisée
SEUIL_SANTE_CRITIQUE = float(os.getenv("SEUIL_SANTE_CRITIQUE", "40"))    # santé sous ce % : plante malade
BONUS_ARROSAGE_MALADIE = 5      # plante en souffrance : arrosage un peu anticipé

# --- Règles en mode crise ---
# 48 h simulées = 8 minutes réelles (480 s). Modifiable : DUREE_CRISE_SECONDES=180 par exemple.
DUREE_CRISE = float(os.getenv("DUREE_CRISE_SECONDES", "480"))
PART_BUDGET_CRISE = 0.40        # le budget d'eau = 40 % de la consommation NORMALE (pas 40 % du réservoir)
CRISE_DUREE_JOUR = 60           # éclairage réduit en crise : 1 min de jour...
CRISE_DUREE_NUIT = 120          # ...et 2 min de nuit, pour limiter l'évaporation
CRISE_MARGE_DEMARRAGE = 5       # zone vitale : pompe ON sous seuil_survie + 5
CRISE_MARGE_ARRET = 10          # zone vitale : pompe OFF au-dessus de seuil_survie + 10

# --- Préréglage "démo de crise" ---
# Après "Préparer la démo de crise", l'arrosage automatique NORMAL est suspendu jusqu'à l'activation de la
# crise, pour que les zones gardent leurs humidités basses. Au bout de ce délai, il reprend tout seul
# (sécurité : la ferme ne reste pas sans arrosage si la crise n'est jamais lancée).
# 45 s : au-delà, les zones ont trop évaporé et la crise consommerait presque tout le budget (voir le calcul).
DUREE_PREPARATION_DEMO = 45

# --- Lecture de zones.json (situé à côté de ce fichier) ---
with open(Path(__file__).parent / "zones.json", encoding="utf-8") as fichier:
    CONFIG = json.load(fichier)

CAPACITE = CONFIG["reservoir_capacite_litres"]        # sert à calculer le pourcentage du réservoir
HUMIDITE_PAR_LITRE = CONFIG["humidite_par_litre"]     # % d'humidité gagnés par litre pompé
TAUX_RECYCLAGE = CONFIG["taux_recyclage"]             # part de l'eau pompée qui revient dans le réservoir (0.9 = 90 %)

# --- État en mémoire : le dernier état connu de chaque zone et du réservoir ---
# None = pas encore reçu de mesure.
etat = {
    "mode": "normal",                    # "normal" ou "crise"
    "fuite_simulee": False,              # dernier ordre de fuite connu (le simulateur ne le publie pas)
    "recyclage_actif": True,             # dernier ordre de recyclage connu (coupé pendant une crise)
    "reservoir_capacite_litres": CAPACITE,
    "reservoir_litres": None,
    "consommation_totale_litres": 0.0,   # total de toutes les zones
    "zones": {},
}
for zone_id, params in CONFIG["zones"].items():
    etat["zones"][zone_id] = {
        # réglages utiles au dashboard
        "nom": params["nom"],
        "vitale": params["vitale"],
        "priorite": params["priorite"],
        "seuil_arrosage": params["seuil_arrosage"],
        "seuil_survie": params["seuil_survie"],
        # dernières mesures reçues
        "humidite": None,
        "temperature": None,
        "ph": None,
        "luminosite": None,
        "pompe": None,      # "ON" ou "OFF"
        "lumiere": None,    # dernière commande de lumière envoyée
        # eau consommée par la pompe de cette zone depuis le démarrage de l'API
        "consommation_litres": 0.0,
        # capteurs réels (pont_capteur.py) : "simulee" ou "capteur-reel", indépendamment pour chaque mesure
        "source_humidite": "simulee",
        "humidite_brute": None,   # valeur brute du capteur d'humidité (utile pour le débogage), None si simulée
        "source_temperature": "simulee",
        # santé des feuilles (%) publiée par CropGuard (module séparé, voir cropguard/), None si inconnue
        "sante_plante": None,
    }

# Liste des alertes, de la plus ancienne à la plus récente.
# Chaque alerte : {"date", "niveau" (info/attention/critique), "zone", "message"}
alertes = []

# Statut actuel de chaque problème, pour ne créer une alerte qu'au CHANGEMENT d'état.
# Exemple : {"survie:zone1": "normal", "reservoir": "attention", "fuite": "normal"}
statuts = {}

# Dernière commande de pompe envoyée à chaque zone. Elle sert à savoir qu'une pompe
# va tourner avant que le simulateur ne l'ait confirmé (au tour suivant).
derniere_commande_pompe = {zone_id: None for zone_id in CONFIG["zones"]}

# Zones qui ont besoin d'eau mais qui attendent (pour ne le noter qu'une fois dans le journal)
zones_en_attente = set()

# --- État de la crise ---
def nouvelle_crise():
    """État d'une crise "vierge" : aucune crise en cours (sert au départ et à la réinitialisation)."""
    return {
        "actif": False,
        "debut": None,                        # heure (time.time()) de l'activation
        "duree_secondes": DUREE_CRISE,
        "consommation_normale_litres": 0.0,   # ce que la ferme consommerait normalement sur la durée
        "budget_total_litres": 0.0,           # 40 % de la consommation normale
        "budget_consomme_litres": 0.0,        # eau pompée depuis le début de la crise
        "paliers_signales": set(),            # paliers de budget (50, 90) déjà signalés
        "refus_signales": set(),              # zones dont le refus de pompe a déjà fait une alerte
        "humidite_min": {},                   # humidité minimale de chaque zone pendant la crise
        "bilan": None,                        # rempli à la fin de la crise
    }


crise = nouvelle_crise()

DEBUT = time.time()   # pour le journal

# Horloge : origine du cycle jour/nuit normal, et demande d'envoi immédiat de l'ordre de lumière
horloge = {"debut_cycle": time.time(), "forcer_envoi": False}

# "ignorer_fuite_jusqua" : sert à ne pas juger les fuites juste après un changement de recyclage
#                         (voir changer_recyclage)
# "demo_jusqua"          : heure jusqu'à laquelle l'arrosage normal est suspendu (préréglage démo de crise)
suivi = {"ignorer_fuite_jusqua": 0.0, "demo_jusqua": 0.0}

# Heure (time.time()) du dernier message reçu de chaque capteur réel : sert à détecter son silence
capteur_reel = {"derniere_reception_humidite": 0.0, "derniere_reception_temperature": 0.0}


def demo_en_attente():
    """Vrai si la démo de crise est préparée et que la crise n'a pas encore été lancée (arrosage normal suspendu)."""
    return not crise["actif"] and time.time() < suivi["demo_jusqua"]

# Client MQTT (paho-mqtt version 2 : il faut préciser la version de l'API)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def journal(texte):
    """Affiche un message précédé du temps écoulé depuis le démarrage."""
    print(f"[{time.time() - DEBUT:6.1f} s] {texte}", flush=True)


# ---------------------------------------------------------------------------
# WaterLoop : consommation d'eau
# ---------------------------------------------------------------------------
def compter_consommation(zone_id):
    """Appelée quand la pompe de la zone tourne : ajoute un tour de débit à sa consommation."""
    debit = CONFIG["zones"][zone_id]["debit_pompe"]
    zone = etat["zones"][zone_id]
    zone["consommation_litres"] = round(zone["consommation_litres"] + debit, 2)
    total = sum(z["consommation_litres"] for z in etat["zones"].values())
    etat["consommation_totale_litres"] = round(total, 2)

    # En crise, cette eau est aussi prélevée sur le budget
    if crise["actif"]:
        crise["budget_consomme_litres"] += debit
        verifier_paliers_budget()


# ---------------------------------------------------------------------------
# WaterLoop : alertes
# ---------------------------------------------------------------------------
def creer_alerte(niveau, zone, message):
    """Ajoute une alerte à la liste et la publie sur spacefarm/alertes."""
    alerte = {
        "date": datetime.now(timezone.utc).isoformat(),
        "niveau": niveau,        # "info", "attention" ou "critique"
        "zone": zone,            # une zone ("zone1"...), "reservoir" ou "crise"
        "message": message,
    }
    alertes.append(alerte)
    del alertes[:-MAX_ALERTES]   # ne garde que les MAX_ALERTES dernières
    client.publish("spacefarm/alertes", json.dumps(alerte, ensure_ascii=False))
    journal(f"ALERTE {niveau} ({zone}) : {message}")


def mettre_a_jour_statut(cle, statut, zone, message, message_retour):
    """
    Crée une alerte seulement si le statut du problème a changé (donc pas de doublon).
      statut = "normal", "attention" ou "critique"
      message = texte de l'alerte si le problème apparaît
      message_retour = texte de l'alerte "info" quand on revient à la normale
    """
    ancien = statuts.get(cle, "normal")
    if statut == ancien:
        return
    statuts[cle] = statut
    if statut == "normal":
        creer_alerte("info", zone, message_retour)
    else:
        creer_alerte(statut, zone, message)


def evaluer_survie(zone_id):
    """Alerte critique si l'humidité de la zone passe sous seuil_survie."""
    zone = etat["zones"][zone_id]
    humidite = zone["humidite"]
    if humidite is None:
        return
    statut = "critique" if humidite < zone["seuil_survie"] else "normal"
    mettre_a_jour_statut(
        f"survie:{zone_id}", statut, zone_id,
        f"{zone['nom']} : humidité {humidite} % sous le seuil de survie ({zone['seuil_survie']} %)",
        f"Retour à la normale : {zone['nom']}, humidité remontée à {humidite} %",
    )


def evaluer_reservoir(ancien_niveau, niveau):
    """Alertes sur le niveau du réservoir et sur les fuites. Appelée à chaque nouveau niveau."""
    # --- Niveau du réservoir : attention sous 30 %, critique sous 10 % ---
    pourcent = niveau / CAPACITE * 100
    if pourcent < SEUIL_RESERVOIR_CRITIQUE:
        statut = "critique"
    elif pourcent < SEUIL_RESERVOIR_BAS:
        statut = "attention"
    else:
        statut = "normal"
    mettre_a_jour_statut(
        "reservoir", statut, "reservoir",
        f"Réservoir {'critique' if statut == 'critique' else 'bas'} : {pourcent:.1f} % ({niveau} L)",
        f"Retour à la normale : réservoir remonté à {pourcent:.1f} % ({niveau} L)",
    )

    # --- Fuite : le réservoir baisse plus que ce que les pompes en marche expliquent ---
    if ancien_niveau is None or any(z["pompe"] is None for z in etat["zones"].values()):
        return   # pas assez d'informations pour juger
    if time.time() < suivi["ignorer_fuite_jusqua"]:
        return   # le recyclage vient de changer : le simulateur peut être au milieu d'un tour
    baisse = ancien_niveau - niveau
    debit_total = sum(CONFIG["zones"][zone_id]["debit_pompe"]
                      for zone_id, zone in etat["zones"].items() if zone["pompe"] == "ON")
    # Avec le recyclage, une part de l'eau pompée revient dans le réservoir : la baisse "normale"
    # est plus petite. Sans cette correction, une fuite pourrait passer inaperçue.
    part_perdue = (1 - TAUX_RECYCLAGE) if etat["recyclage_actif"] else 1
    attendu = debit_total * part_perdue
    statut = "critique" if baisse - attendu > TOLERANCE_FUITE else "normal"
    mettre_a_jour_statut(
        "fuite", statut, "reservoir",
        f"Fuite suspectée : le réservoir a perdu {baisse:.1f} L en un tour, les pompes n'expliquent que {attendu:.1f} L",
        "Retour à la normale : la baisse du réservoir correspond de nouveau aux pompes, plus de fuite",
    )


def evaluer_chaleur(zone_id):
    """Alerte "attention" si la température de la zone dépasse le seuil de chaleur (module ajouté
    par un membre de l'équipe : sert aussi à avancer l'arrosage, voir seuil_demarrage)."""
    zone = etat["zones"][zone_id]
    t = zone["temperature"]
    if t is None:
        return
    statut = "attention" if t >= SEUIL_TEMP_CHALEUR else "normal"
    mettre_a_jour_statut(
        f"chaleur:{zone_id}", statut, zone_id,
        f"{zone['nom']} : température élevée {t} degrés (seuil {SEUIL_TEMP_CHALEUR:.0f}) - arrosage anticipé",
        f"Retour à la normale : {zone['nom']}, température redescendue à {t} degrés",
    )


def evaluer_maladie(zone_id):
    """Alerte quand CropGuard (module séparé, voir cropguard/) signale une plante en souffrance
    (santé basse) sur cette zone. Sert aussi à avancer l'arrosage, voir seuil_demarrage."""
    zone = etat["zones"][zone_id]
    sante = zone.get("sante_plante")
    if sante is None:
        return
    if sante < SEUIL_SANTE_CRITIQUE:
        statut = "critique"
    elif sante < SEUIL_SANTE_ATTENTION:
        statut = "attention"
    else:
        statut = "normal"
    mettre_a_jour_statut(
        f"maladie:{zone_id}", statut, zone_id,
        f"CropGuard : {zone['nom']} en souffrance (santé des feuilles {sante} %) - arrosage anticipé",
        f"Retour à la normale : {zone['nom']}, santé des feuilles remontée à {sante} %",
    )


# ---------------------------------------------------------------------------
# Mode crise : budget d'eau, début et fin
# ---------------------------------------------------------------------------
def calculer_consommation_normale(duree_secondes):
    """
    Eau qu'il faudrait NORMALEMENT pour compenser l'évaporation de toutes les zones
    pendant duree_secondes, avec le cycle jour/nuit normal.
    """
    tours = duree_secondes / INTERVALLE
    # eau par tour de jour = évaporation (%) / humidité gagnée par litre (%/L), toutes zones ensemble
    litres_par_tour_de_jour = sum(p["evaporation"] for p in CONFIG["zones"].values()) / HUMIDITE_PAR_LITRE
    # la nuit l'évaporation est divisée par 2 : on fait la moyenne sur un cycle jour/nuit normal
    part_jour = DUREE_JOUR / (DUREE_JOUR + DUREE_NUIT)
    facteur_jour_nuit = part_jour + (1 - part_jour) / 2
    return tours * litres_par_tour_de_jour * facteur_jour_nuit


def budget_restant():
    """Litres qu'il reste à dépenser sur le budget de la crise."""
    return crise["budget_total_litres"] - crise["budget_consomme_litres"]


def budget_permet_un_tour(zone_id):
    """Vrai s'il reste assez de budget pour que la pompe de la zone tourne encore UN tour."""
    debit = CONFIG["zones"][zone_id]["debit_pompe"]
    return budget_restant() >= debit - 1e-9   # 1e-9 : évite les erreurs d'arrondi des décimaux


def signaler_budget_insuffisant(zone_id):
    """Crée une alerte critique (une seule fois par zone et par crise) : la pompe est refusée."""
    if zone_id in crise["refus_signales"]:
        return
    crise["refus_signales"].add(zone_id)
    zone = etat["zones"][zone_id]
    debit = CONFIG["zones"][zone_id]["debit_pompe"]
    creer_alerte(
        "critique", zone_id,
        f"Budget d'eau de crise insuffisant : pompe {zone['nom']} refusée "
        f"(il reste {budget_restant():.2f} L, un tour demande {debit} L)",
    )


def verifier_paliers_budget():
    """Alertes "attention" quand 50 % puis 90 % du budget sont consommés."""
    if crise["budget_total_litres"] <= 0:
        return
    pourcent = crise["budget_consomme_litres"] / crise["budget_total_litres"] * 100
    for palier in (50, 90):
        if pourcent >= palier and palier not in crise["paliers_signales"]:
            crise["paliers_signales"].add(palier)
            creer_alerte(
                "attention", "crise",
                f"Budget d'eau de crise consommé à {palier} % "
                f"({crise['budget_consomme_litres']:.1f} L sur {crise['budget_total_litres']:.1f} L)",
            )


def publier_mode(mode):
    """Publie le mode ("normal" ou "crise") sur spacefarm/mode. Message conservé par le broker (retain)."""
    etat["mode"] = mode
    message = {"valeur": mode, "unite": "", "date": datetime.now(timezone.utc).isoformat()}
    client.publish("spacefarm/mode", json.dumps(message), retain=True)


def changer_recyclage(actif):
    """
    Coupe (False) ou rétablit (True) le recyclage de l'eau dans le simulateur.
    Message conservé par le broker (retain) : un simulateur lancé après nous reçoit quand même l'ordre.
    """
    if etat["recyclage_actif"] != actif:
        # Un tour du simulateur peut être en cours : on ne juge pas les fuites pendant deux tours
        suivi["ignorer_fuite_jusqua"] = time.time() + 2 * INTERVALLE
    etat["recyclage_actif"] = actif
    client.publish("spacefarm/recyclage", "ON" if actif else "OFF", retain=True)
    journal(f"Recyclage de l'eau : {'actif' if actif else 'coupé'}")


def activer_crise():
    """Démarre la crise : calcule le budget, coupe les zones non vitales, publie le mode."""
    if crise["actif"]:
        return   # déjà en crise

    normale = calculer_consommation_normale(DUREE_CRISE)
    crise["actif"] = True
    crise["debut"] = time.time()
    crise["duree_secondes"] = DUREE_CRISE
    crise["consommation_normale_litres"] = normale
    crise["budget_total_litres"] = PART_BUDGET_CRISE * normale
    crise["budget_consomme_litres"] = 0.0
    crise["paliers_signales"] = set()
    crise["refus_signales"] = set()
    crise["humidite_min"] = {zone_id: zone["humidite"] for zone_id, zone in etat["zones"].items()}
    crise["bilan"] = None
    suivi["demo_jusqua"] = 0.0   # la crise commence : la suspension de l'arrosage du préréglage est terminée

    publier_mode("crise")
    changer_recyclage(False)   # l'eau recyclée est contaminée : on coupe le recyclage
    creer_alerte(
        "critique", "crise",
        f"Crise activée (contamination du recyclage) : budget d'eau {crise['budget_total_litres']:.1f} L "
        f"pour {DUREE_CRISE:.0f} s, soit {PART_BUDGET_CRISE * 100:.0f} % de la consommation normale "
        f"({normale:.1f} L). Zones non vitales sacrifiées.",
    )

    # Les zones non vitales sont sacrifiées : pompe coupée immédiatement
    for zone_id, zone in etat["zones"].items():
        if not zone["vitale"]:
            envoyer_pompe(zone_id, "OFF", "crise : zone non vitale sacrifiée")


def terminer_crise(origine):
    """Termine la crise (origine = "automatique" ou "manuelle") : bilan, alerte, retour au mode normal."""
    if not crise["actif"]:
        return
    crise["actif"] = False
    duree_reelle = time.time() - crise["debut"]
    consomme = crise["budget_consomme_litres"]
    total = crise["budget_total_litres"]

    # Zones vitales dont l'humidité est descendue sous le seuil de survie pendant la crise
    sous_survie = [
        zone_id for zone_id, zone in etat["zones"].items()
        if zone["vitale"]
        and crise["humidite_min"].get(zone_id) is not None
        and crise["humidite_min"][zone_id] < zone["seuil_survie"]
    ]
    crise["bilan"] = {
        "origine": origine,
        "duree_reelle_secondes": round(duree_reelle, 1),
        "budget_total_litres": round(total, 2),
        "budget_consomme_litres": round(consomme, 2),
        "budget_utilise_pourcent": round(consomme / total * 100, 1) if total > 0 else 0,
        "humidite_min": {z: (round(h, 1) if h is not None else None) for z, h in crise["humidite_min"].items()},
        "zones_vitales_sous_survie": sous_survie,
    }

    publier_mode("normal")
    changer_recyclage(True)   # fin de la crise : le recyclage est rétabli

    minimums = ", ".join(
        f"{zone_id} {etat['zones'][zone_id]['nom']} {h:.1f} %"
        for zone_id, h in crise["humidite_min"].items() if h is not None
    )
    if sous_survie:
        verdict = "ATTENTION : zones vitales passées sous le seuil de survie : " + ", ".join(sous_survie)
    else:
        verdict = "Toutes les zones vitales sont restées au-dessus du seuil de survie."
    creer_alerte(
        "info", "crise",
        f"Fin de crise ({origine}) : {consomme:.1f} L consommés sur {total:.1f} L "
        f"({crise['bilan']['budget_utilise_pourcent']:.0f} % du budget) en {duree_reelle:.0f} s. "
        f"Humidité minimale : {minimums}. {verdict}",
    )


def construire_statut_crise():
    """Contenu de GET /crise."""
    actif = crise["actif"]
    if actif:
        temps_restant = max(0.0, crise["duree_secondes"] - (time.time() - crise["debut"]))
    else:
        temps_restant = 0.0

    # Zones en danger : humidité sous le seuil de survie (les zones sacrifiées y seront forcément)
    zones_en_danger = [
        {"zone": zone_id, "nom": zone["nom"], "vitale": zone["vitale"],
         "humidite": zone["humidite"], "seuil_survie": zone["seuil_survie"]}
        for zone_id, zone in etat["zones"].items()
        if zone["humidite"] is not None and zone["humidite"] < zone["seuil_survie"]
    ]
    return {
        "actif": actif,
        "temps_restant_secondes": round(temps_restant, 1),
        "duree_secondes": crise["duree_secondes"],
        "consommation_normale_litres": round(crise["consommation_normale_litres"], 2),
        "budget_total_litres": round(crise["budget_total_litres"], 2),
        "budget_consomme_litres": round(crise["budget_consomme_litres"], 2),
        "budget_restant_litres": round(budget_restant(), 2),
        "zones_en_danger": zones_en_danger,
        "bilan": crise["bilan"],   # rempli quand la crise est terminée
    }


# ---------------------------------------------------------------------------
# Règle d'arrosage et priorité de l'eau
# ---------------------------------------------------------------------------
def reservoir_bas():
    """Vrai si le réservoir est sous SEUIL_RESERVOIR_BAS % de sa capacité."""
    niveau = etat["reservoir_litres"]
    return niveau is not None and niveau / CAPACITE * 100 < SEUIL_RESERVOIR_BAS


def restriction_active():
    """Vrai quand l'eau est rationnée : en crise, ou quand le réservoir est bas."""
    return crise["actif"] or reservoir_bas()


def seuil_demarrage(zone):
    """Humidité sous laquelle on allume la pompe de la zone."""
    if crise["actif"]:
        return zone["seuil_survie"] + CRISE_MARGE_DEMARRAGE    # crise : juste au-dessus de la survie
    seuil = zone["seuil_arrosage"]
    # Il fait chaud : on arrose plus tôt (les plantes perdent l'eau plus vite)
    if zone.get("temperature") is not None and zone["temperature"] >= SEUIL_TEMP_CHALEUR:
        seuil += BONUS_ARROSAGE_CHALEUR
    # Plante en souffrance signalée par CropGuard : on arrose un peu plus tôt
    if zone.get("sante_plante") is not None and zone["sante_plante"] < SEUIL_SANTE_ATTENTION:
        seuil += BONUS_ARROSAGE_MALADIE
    # Plafond : on reste sous le seuil d'arrêt pour garder l'hystérésis (pas d'allumage/extinction en boucle)
    return min(seuil, zone["seuil_arrosage"] + MARGE_ARRET_POMPE - 2)


def seuil_arret(zone):
    """Humidité au-dessus de laquelle on éteint la pompe de la zone."""
    if crise["actif"]:
        return zone["seuil_survie"] + CRISE_MARGE_ARRET
    return zone["seuil_arrosage"] + MARGE_ARRET_POMPE


def pompe_en_marche(zone_id):
    """Vrai si la pompe tourne (ou va tourner : on tient compte de la dernière commande envoyée)."""
    commande = derniere_commande_pompe[zone_id]
    if commande is not None:
        return commande == "ON"
    return etat["zones"][zone_id]["pompe"] == "ON"


def arrosage_autorise(zone_id):
    """
    Utilisée quand l'eau est rationnée (crise ou réservoir bas) : la zone a-t-elle le droit
    de démarrer sa pompe ?
      - zone non vitale : jamais ;
      - zone vitale : seulement si aucune autre pompe vitale ne tourne et si aucune
        zone vitale plus prioritaire (priorite plus petite) n'attend de l'eau.
    """
    zone = etat["zones"][zone_id]
    if not zone["vitale"]:
        return False

    for autre_id, autre in etat["zones"].items():
        if autre_id == zone_id or not autre["vitale"]:
            continue
        if pompe_en_marche(autre_id):
            return False   # une autre pompe vitale tourne déjà : une seule à la fois
        a_besoin_d_eau = autre["humidite"] is not None and autre["humidite"] < seuil_demarrage(autre)
        if a_besoin_d_eau and autre["priorite"] < zone["priorite"]:
            return False   # une zone plus prioritaire attend : elle passe en premier
    return True


def envoyer_pompe(zone_id, ordre, raison):
    """Envoie ON ou OFF à la pompe d'une zone et le note dans le journal."""
    client.publish(f"spacefarm/{zone_id}/cmd/pompe", ordre)
    derniere_commande_pompe[zone_id] = ordre
    journal(f"{zone_id} ({etat['zones'][zone_id]['nom']}) : {raison} -> pompe {ordre}")


def appliquer_regle_arrosage(zone_id):
    """Décide s'il faut allumer ou éteindre la pompe de la zone (règles normales ou de crise)."""
    zone = etat["zones"][zone_id]
    humidite = zone["humidite"]
    pompe = zone["pompe"]
    if humidite is None or pompe is None:
        return   # on n'a pas encore toutes les infos
    if demo_en_attente():
        return   # démo de crise préparée : on laisse les humidités basses jusqu'au lancement de la crise

    seuil_on = seuil_demarrage(zone)
    seuil_off = seuil_arret(zone)

    if pompe == "ON":
        # Arrêt normal : la zone est assez humide
        if humidite > seuil_off:
            envoyer_pompe(zone_id, "OFF", f"humidité {humidite} % > {seuil_off} %")
        # Arrêt de priorité : l'eau est réservée aux zones vitales
        elif restriction_active() and not zone["vitale"]:
            raison = "crise : zone sacrifiée" if crise["actif"] else "réservoir bas, l'eau est réservée aux zones vitales"
            envoyer_pompe(zone_id, "OFF", raison)
        # Arrêt de budget : en crise, pas assez d'eau pour un tour de plus
        elif crise["actif"] and not budget_permet_un_tour(zone_id):
            envoyer_pompe(zone_id, "OFF", "budget de crise épuisé")
            signaler_budget_insuffisant(zone_id)

    elif humidite < seuil_on:
        reservoir = etat["reservoir_litres"]
        if reservoir is not None and reservoir <= 0:
            return   # réservoir vide : inutile d'envoyer ON

        if restriction_active() and not arrosage_autorise(zone_id):
            # On ne le note dans le journal qu'une fois, pas à chaque tour
            if zone_id not in zones_en_attente:
                zones_en_attente.add(zone_id)
                raison = "crise" if crise["actif"] else "réservoir bas, priorité de l'eau"
                journal(f"{zone_id} ({zone['nom']}) : humidité {humidite} % < {seuil_on} %, "
                        f"arrosage retenu ({raison})")
            return

        # En crise, le budget ne doit JAMAIS être dépassé : on refuse si un tour ne passe pas
        if crise["actif"] and not budget_permet_un_tour(zone_id):
            signaler_budget_insuffisant(zone_id)
            return

        zones_en_attente.discard(zone_id)
        envoyer_pompe(zone_id, "ON", f"humidité {humidite} % < {seuil_on} %")

    else:
        zones_en_attente.discard(zone_id)   # la zone n'a plus besoin d'eau


# ---------------------------------------------------------------------------
# Capteurs réels (pont_capteur.py)
# ---------------------------------------------------------------------------
def traiter_mesure_humidite_reelle(zone_id, payload):
    """
    Message reçu sur spacefarm/<zone>/humidite_reelle (pont_capteur.py branché sur un vrai capteur) :
    remplace l'humidité SIMULÉE de la zone par cette mesure. Les autres mesures (pH, luminosité) et
    la pompe restent simulées ; la température a sa propre bascule, voir traiter_mesure_temperature_reelle.
    """
    if zone_id != ZONE_CAPTEUR_REEL or zone_id not in etat["zones"]:
        return   # capteur non prévu pour cette zone (ou zone inconnue) : on ignore par sécurité
    try:
        message = json.loads(payload)
        valeur = float(message["valeur"])
    except (ValueError, KeyError, TypeError):
        return   # message mal formé : on l'ignore plutôt que de planter

    zone = etat["zones"][zone_id]
    nouvelle_connexion = zone["source_humidite"] != "capteur-reel"
    # On écrit la valeur AVANT de basculer le drapeau "source" : l'API tourne sur deux fils
    # d'exécution (MQTT et HTTP), et un lecteur qui verrait le drapeau changé avant la valeur
    # (GET /etat au mauvais moment) recevrait une valeur encore périmée.
    zone["humidite"] = valeur
    zone["humidite_brute"] = message.get("brut")
    capteur_reel["derniere_reception_humidite"] = time.time()
    zone["source_humidite"] = "capteur-reel"
    if nouvelle_connexion:
        creer_alerte("info", zone_id, f"Capteur d'humidité réel connecté : {zone['nom']} suit désormais la mesure réelle (plus la simulation).")

    # En crise, on retient l'humidité la plus basse de la zone (pour le bilan), comme pour la simulation
    if crise["actif"]:
        minimum = crise["humidite_min"].get(zone_id)
        crise["humidite_min"][zone_id] = valeur if minimum is None else min(minimum, valeur)

    # On applique les règles tout de suite (et pas seulement au prochain "pompe" du simulateur) :
    # avec un capteur réel, on veut réagir dès que l'humidité change (par exemple pour la démo).
    evaluer_survie(zone_id)
    appliquer_regle_arrosage(zone_id)


def traiter_mesure_temperature_reelle(zone_id, payload):
    """
    Message reçu sur spacefarm/<zone>/temperature_reelle : remplace la température SIMULÉE de la
    zone. Sert à l'affichage, et (voir evaluer_chaleur / seuil_demarrage) à avancer un peu
    l'arrosage si la zone a trop chaud ; n'influence pas les autres règles (crise, priorité).
    """
    if zone_id != ZONE_CAPTEUR_REEL or zone_id not in etat["zones"]:
        return
    try:
        message = json.loads(payload)
        valeur = float(message["valeur"])
    except (ValueError, KeyError, TypeError):
        return

    zone = etat["zones"][zone_id]
    nouvelle_connexion = zone["source_temperature"] != "capteur-reel"
    # Même ordre que pour l'humidité : la valeur avant le drapeau (voir traiter_mesure_humidite_reelle)
    zone["temperature"] = valeur
    capteur_reel["derniere_reception_temperature"] = time.time()
    zone["source_temperature"] = "capteur-reel"
    if nouvelle_connexion:
        creer_alerte("info", zone_id, f"Capteur de température réel connecté : {zone['nom']} suit désormais la mesure réelle (plus la simulation).")
    evaluer_chaleur(zone_id)   # avec une vraie mesure aussi, pas seulement en simulation


def verifier_capteur_reel():
    """Si plus aucune mesure réelle depuis DELAI_CAPTEUR_REEL secondes, la mesure concernée repasse
    en simulée. Humidité et température sont vérifiées indépendamment : un seul fil qui lâche
    (câblage, capteur défectueux) ne fait pas repasser l'autre mesure en simulé."""
    zone = etat["zones"].get(ZONE_CAPTEUR_REEL)
    if zone is None:
        return
    maintenant = time.time()

    if zone["source_humidite"] == "capteur-reel" and maintenant - capteur_reel["derniere_reception_humidite"] > DELAI_CAPTEUR_REEL:
        zone["source_humidite"] = "simulee"
        zone["humidite_brute"] = None
        creer_alerte(
            "info", ZONE_CAPTEUR_REEL,
            f"Capteur d'humidité réel silencieux depuis {DELAI_CAPTEUR_REEL:.0f} s : {zone['nom']} repasse en humidité simulée.",
        )

    if zone["source_temperature"] == "capteur-reel" and maintenant - capteur_reel["derniere_reception_temperature"] > DELAI_CAPTEUR_REEL:
        zone["source_temperature"] = "simulee"
        creer_alerte(
            "info", ZONE_CAPTEUR_REEL,
            f"Capteur de température réel silencieux depuis {DELAI_CAPTEUR_REEL:.0f} s : {zone['nom']} repasse en température simulée.",
        )


# ---------------------------------------------------------------------------
# MQTT : réception des mesures
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    """Appelée à la connexion (et à chaque reconnexion) : on s'abonne à tout."""
    journal(f"Connecté au broker {BROKER_HOST}:{BROKER_PORT}")
    client.subscribe("spacefarm/#")
    client.subscribe("cropguard/#")   # santé des plantes publiée par CropGuard (module séparé)
    # On (re)publie le mode et le recyclage : efface un éventuel "crise" / "OFF" resté dans le broker
    # d'une exécution précédente
    publier_mode("crise" if crise["actif"] else "normal")
    changer_recyclage(not crise["actif"])


def on_message(client, userdata, msg):
    """Appelée à chaque message. On garde la valeur reçue dans 'etat'."""
    # Ordre de fuite simulée (envoyé par la route POST ou par mosquitto_pub) : texte simple ON/OFF, pas de JSON.
    # On le mémorise pour que le dashboard puisse afficher le bon bouton, même après un rechargement de page.
    if msg.topic == "spacefarm/simulation/fuite":
        ordre = msg.payload.decode(errors="ignore").strip().upper()
        if ordre in ("ON", "OFF"):
            etat["fuite_simulee"] = (ordre == "ON")
        return

    # Ordre de recyclage (envoyé par nous ou par mosquitto_pub) : texte simple ON/OFF, on mémorise l'état
    if msg.topic == "spacefarm/recyclage":
        ordre = msg.payload.decode(errors="ignore").strip().upper()
        if ordre in ("ON", "OFF"):
            actif = (ordre == "ON")
            if etat["recyclage_actif"] != actif:
                suivi["ignorer_fuite_jusqua"] = time.time() + 2 * INTERVALLE
            etat["recyclage_actif"] = actif
        return

    # Santé des plantes publiée par CropGuard (module séparé, voir cropguard/) : cropguard/<zone>/sante
    if msg.topic.startswith("cropguard/") and msg.topic.endswith("/sante"):
        zone_id = msg.topic.split("/")[1]
        try:
            valeur = json.loads(msg.payload)["valeur"]
        except (ValueError, KeyError, TypeError):
            return
        if zone_id in etat["zones"]:
            etat["zones"][zone_id]["sante_plante"] = valeur
            evaluer_maladie(zone_id)
        return
    if msg.topic.startswith("cropguard/"):
        return   # autres topics CropGuard (alertes...) : on ne s'en sert pas ici

    morceaux = msg.topic.split("/")   # ex. ["spacefarm", "zone1", "humidite"]
    if len(morceaux) != 3:
        return   # on ignore les commandes (4 morceaux), nos alertes et le mode (2 morceaux)

    _, cible, mesure = morceaux

    # Mesures des capteurs réels (pont_capteur.py), format différent (avec "source") : traitées à part
    if mesure == "humidite_reelle":
        traiter_mesure_humidite_reelle(cible, msg.payload)
        return
    if mesure == "temperature_reelle":
        traiter_mesure_temperature_reelle(cible, msg.payload)
        return

    try:
        valeur = json.loads(msg.payload)["valeur"]
    except (ValueError, KeyError, TypeError):
        return   # message qui n'a pas le format {"valeur": ...} (ex. spacefarm/simulation/fuite) : on l'ignore

    if cible == "reservoir" and mesure == "niveau":
        ancien_niveau = etat["reservoir_litres"]
        etat["reservoir_litres"] = valeur
        evaluer_reservoir(ancien_niveau, valeur)

    elif cible in etat["zones"] and mesure in ("humidite", "temperature", "ph", "luminosite", "pompe"):
        # Capteur(s) réel(s) actif(s) sur cette zone : on ignore la mesure SIMULÉE correspondante
        # (les autres mesures et la pompe restent simulées, indépendamment de l'humidité et de la température).
        if mesure == "humidite" and cible == ZONE_CAPTEUR_REEL and etat["zones"][cible]["source_humidite"] == "capteur-reel":
            return
        if mesure == "temperature" and cible == ZONE_CAPTEUR_REEL and etat["zones"][cible]["source_temperature"] == "capteur-reel":
            return
        etat["zones"][cible][mesure] = valeur

        # En crise, on retient l'humidité la plus basse de chaque zone (pour le bilan)
        if mesure == "humidite" and crise["actif"]:
            minimum = crise["humidite_min"].get(cible)
            crise["humidite_min"][cible] = valeur if minimum is None else min(minimum, valeur)

        # Le simulateur publie "pompe" en dernier à chaque tour : à ce moment,
        # l'humidité et l'état de la pompe sont à jour, donc on applique les règles ici.
        if mesure == "pompe":
            derniere_commande_pompe[cible] = None   # l'état réel est connu, on oublie la commande
            if valeur == "ON":
                compter_consommation(cible)
            evaluer_survie(cible)
            appliquer_regle_arrosage(cible)

        # Réaction à la température : chaleur -> alerte + arrosage anticipé (voir seuil_demarrage)
        if mesure == "temperature":
            evaluer_chaleur(cible)


# ---------------------------------------------------------------------------
# Horloge : cycle jour/nuit et fin de crise (tourne dans un fil d'exécution séparé)
# ---------------------------------------------------------------------------
def phase_lumiere():
    """Renvoie "ON" (jour) ou "OFF" (nuit) selon le mode : normal (2 min/1 min) ou crise (1 min/2 min)."""
    if crise["actif"]:
        position = (time.time() - crise["debut"]) % (CRISE_DUREE_JOUR + CRISE_DUREE_NUIT)
        return "ON" if position < CRISE_DUREE_JOUR else "OFF"
    position = (time.time() - horloge["debut_cycle"]) % (DUREE_JOUR + DUREE_NUIT)
    return "ON" if position < DUREE_JOUR else "OFF"


def boucle_horloge():
    """Toutes les secondes : termine la crise si sa durée est écoulée, et gère la lumière."""
    derniere_phase = None
    dernier_envoi = 0

    while True:
        try:
            # Fin automatique de la crise : retour au mode normal
            if crise["actif"] and time.time() - crise["debut"] >= crise["duree_secondes"]:
                terminer_crise("automatique")

            # Capteur réel silencieux depuis trop longtemps : retour à l'humidité simulée
            verifier_capteur_reel()

            phase = phase_lumiere()

            # On envoie quand la phase change, et aussi toutes les 10 s : ainsi le
            # simulateur reçoit l'ordre même s'il démarre après l'API.
            if phase != derniere_phase or horloge["forcer_envoi"] or time.time() - dernier_envoi >= 10:
                horloge["forcer_envoi"] = False
                if phase != derniere_phase:
                    texte = "Jour : lumière ON" if phase == "ON" else "Nuit : lumière OFF"
                    journal(texte + (" (cycle de crise)" if crise["actif"] else ""))
                for zone_id in etat["zones"]:
                    client.publish(f"spacefarm/{zone_id}/cmd/lumiere", phase)
                    etat["zones"][zone_id]["lumiere"] = phase
                derniere_phase = phase
                dernier_envoi = time.time()
        except Exception as erreur:   # l'horloge ne doit jamais s'arrêter (sinon la crise ne finirait pas)
            journal(f"Erreur dans l'horloge : {erreur!r}")

        time.sleep(1)


# ---------------------------------------------------------------------------
# Réinitialisation (pour préparer la démo)
# ---------------------------------------------------------------------------
def reinitialiser_ferme(demo=False):
    """
    Remet la ferme à zéro : plus de crise, plus de fuite, recyclage actif, compteurs à zéro,
    alertes vidées, nouveau cycle jour/nuit. Le réservoir et les humidités sont remis à leur
    valeur de départ par le simulateur (au début de son prochain tour, donc dans les 2 secondes).

    demo=True : préréglage "démo de crise". Même remise à zéro, mais les humidités repartent des valeurs
    "humidite_demo_crise" de zones.json (proches des seuils de survie) et l'arrosage normal est suspendu
    pendant DUREE_PREPARATION_DEMO secondes, ou jusqu'à l'activation de la crise.
    """
    # 1. Plus de crise (on remet l'état à zéro sans créer d'alerte de fin)
    crise.update(nouvelle_crise())
    publier_mode("normal")
    changer_recyclage(True)

    # 2. Plus de fuite
    etat["fuite_simulee"] = False
    client.publish("spacefarm/simulation/fuite", "OFF")

    # 3. Compteurs de consommation, alertes et mémoire des règles
    etat["consommation_totale_litres"] = 0.0
    for zone_id, zone in etat["zones"].items():
        zone["consommation_litres"] = 0.0
        derniere_commande_pompe[zone_id] = None
        # Capteurs réels : on repart en simulé. S'ils sont toujours branchés, leur prochain message
        # (moins de 2 s) rebascule la zone tout seul ; sinon la démo repart bien sur du simulé.
        zone["source_humidite"] = "simulee"
        zone["humidite_brute"] = None
        zone["source_temperature"] = "simulee"
        zone["sante_plante"] = None
    capteur_reel["derniere_reception_humidite"] = 0.0
    capteur_reel["derniere_reception_temperature"] = 0.0
    alertes.clear()
    statuts.clear()
    zones_en_attente.clear()

    # 4. Nouveau jour : le cycle de lumière repart et l'ordre est renvoyé tout de suite
    horloge["debut_cycle"] = time.time()
    horloge["forcer_envoi"] = True

    # 5. Réservoir, humidités, pompes : c'est le simulateur qui les remet à zéro
    #    (message "DEMO" : il repart des humidités du préréglage de démo de crise)
    suivi["demo_jusqua"] = (time.time() + DUREE_PREPARATION_DEMO) if demo else 0.0
    client.publish("spacefarm/simulation/reinitialiser", "DEMO" if demo else "ON")
    journal("Ferme réinitialisée pour la démo de crise (arrosage normal suspendu jusqu'à la crise, "
            f"{DUREE_PREPARATION_DEMO} s au maximum)" if demo else "Ferme réinitialisée")


# ---------------------------------------------------------------------------
# API FastAPI
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    """Démarrage : on lance MQTT et l'horloge. Arrêt : on ferme MQTT."""
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(BROKER_HOST, BROKER_PORT)   # se reconnecte tout seul si le broker est absent
    client.loop_start()                              # MQTT tourne en arrière-plan
    threading.Thread(target=boucle_horloge, daemon=True).start()
    yield
    client.loop_stop()
    client.disconnect()


app = FastAPI(title="SpaceFarm API", lifespan=lifespan)

# CORS : autorise le dashboard React (autre port) à appeler cette API.
# "*" = toutes les origines, acceptable pour un workshop en local.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/etat")
def lire_etat():
    """Dernier état connu de toutes les zones et du réservoir, avec la consommation d'eau."""
    # Démo de crise préparée ? (et combien de secondes il reste avant que l'arrosage normal reprenne)
    etat["demo_crise_prete"] = demo_en_attente()
    etat["demo_crise_secondes_restantes"] = max(0, round(suivi["demo_jusqua"] - time.time())) if demo_en_attente() else 0
    return etat


@app.get("/alertes")
def lire_alertes():
    """Liste des alertes, de la plus ancienne à la plus récente."""
    return alertes


@app.post("/simulation/fuite")
def simuler_fuite(ordre: Annotated[Literal["ON", "OFF"], Query(alias="etat")]):
    """Déclenche (ON) ou arrête (OFF) la fuite simulée. Exemple : POST /simulation/fuite?etat=ON"""
    # Le paramètre s'appelle "etat" dans l'URL mais "ordre" ici, pour ne pas
    # cacher le dictionnaire global "etat".
    etat["fuite_simulee"] = (ordre == "ON")   # mémorisé tout de suite (le message MQTT revient ensuite aussi)
    client.publish("spacefarm/simulation/fuite", ordre)
    journal(f"Simulation de fuite : {ordre}")
    return {"fuite": ordre}


@app.get("/crise")
def lire_crise():
    """Statut de la crise : actif, temps restant, budget total / consommé / restant, zones en danger."""
    return construire_statut_crise()


@app.post("/crise/activer")
def route_activer_crise():
    """Déclenche la crise (sans effet si elle est déjà en cours)."""
    activer_crise()
    return construire_statut_crise()


@app.post("/crise/desactiver")
def route_desactiver_crise():
    """Termine la crise avant la fin du temps prévu (sans effet si aucune crise n'est en cours)."""
    terminer_crise("manuelle")
    return construire_statut_crise()


@app.post("/reinitialiser")
def route_reinitialiser():
    """Remet la ferme à zéro (réservoir plein, humidités de départ, compteurs, alertes) et arrête fuite et crise."""
    reinitialiser_ferme()
    return {"reinitialise": True}


@app.post("/preparer-demo-crise")
def route_preparer_demo_crise():
    """
    Réinitialisation complète, avec des humidités de départ proches des seuils de survie ("une ferme
    qui a déjà souffert"), pour qu'une crise de 3 minutes montre le rationnement.
    À suivre, dans les 45 secondes, d'un POST /crise/activer.
    """
    reinitialiser_ferme(demo=True)
    return {"demo_preparee": True, "secondes_pour_lancer_la_crise": DUREE_PREPARATION_DEMO}
