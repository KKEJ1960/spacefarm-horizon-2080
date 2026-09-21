r"""
Test de la réinitialisation de la ferme (POST /reinitialiser, bouton "Réinitialiser la ferme").

Ce script lance tout seul l'API et le simulateur, puis vérifie que la réinitialisation remet tout à
zéro dans trois situations :
  A. en fonctionnement normal, après un peu d'activité (pompes, consommation) ;
  B. pendant une fuite ;
  C. pendant une crise.
"Tout à zéro" = réservoir à 200 L, humidités de départ, compteurs de consommation à 0, alertes vides,
plus de fuite ni de crise, recyclage actif.

Il faut que le broker Mosquitto tourne déjà (conteneur Docker mosquitto-workshop).
Aucune autre API ni simulateur ne doit être en cours d'exécution.
Ce test appelle la route de l'API : il ne clique pas sur le bouton du dashboard.

Depuis la RACINE du projet, en PowerShell (durée : environ 1 minute 30) :
    spacefarm\.venv\Scripts\python.exe tests\test_reinit.py

Code de sortie : 0 si toutes les vérifications passent, 1 sinon.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_SPACEFARM = RACINE / "spacefarm"
API = "http://127.0.0.1:8000"     # 127.0.0.1 plutôt que localhost : plus rapide sous Windows
HUMIDITE_DEPART = 70.0            # valeur par défaut du simulateur


def appeler(methode, chemin):
    """Appelle l'API HTTP et renvoie la réponse JSON."""
    requete = urllib.request.Request(API + chemin, method=methode)
    with urllib.request.urlopen(requete, timeout=5) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def lancer(nom, arguments, variables, dossier_logs):
    """Lance un programme Python du dossier spacefarm, avec ses messages dans un fichier de log."""
    log = open(Path(dossier_logs) / f"{nom}.log", "w", encoding="utf-8")
    return subprocess.Popen([sys.executable] + arguments, cwd=DOSSIER_SPACEFARM, env=variables,
                            stdout=log, stderr=subprocess.STDOUT)


def arreter(processus):
    """Arrête un programme lancé, avec ses processus enfants (sous Windows, le python du venv en crée un)."""
    if processus is None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(processus.pid), "/T", "/F"], capture_output=True)
    else:
        processus.terminate()


def photo():
    """L'état complet de la ferme vu par l'API."""
    etat = appeler("GET", "/etat")
    crise = appeler("GET", "/crise")
    alertes = appeler("GET", "/alertes")
    return etat, crise, alertes


def resume(etat, crise, alertes):
    zones = etat["zones"].values()
    return (f"réservoir {etat['reservoir_litres']} L | humidités {'/'.join(str(z['humidite']) for z in zones)} | "
            f"consommation {etat['consommation_totale_litres']} L | alertes {len(alertes)} | fuite {etat['fuite_simulee']} | "
            f"crise {crise['actif']} | recyclage {etat['recyclage_actif']}")


def est_a_zero(etat, crise, alertes):
    """Vrai si la ferme est "à zéro". Les humidités ont pu perdre quelques points depuis la remise à 70 %."""
    zones = etat["zones"].values()
    return (etat["reservoir_litres"] >= 199.9
            and all(HUMIDITE_DEPART - 4 <= z["humidite"] <= HUMIDITE_DEPART for z in zones)
            and etat["consommation_totale_litres"] == 0 and all(z["consommation_litres"] == 0 for z in zones)
            and alertes == [] and etat["fuite_simulee"] is False
            and crise["actif"] is False and crise["budget_total_litres"] == 0 and crise["bilan"] is None
            and etat["mode"] == "normal" and etat["recyclage_actif"] is True)


resultats = []


def verifier(nom, ok, detail):
    resultats.append(ok)
    print(f"[{'OK' if ok else 'ECHEC'}] {nom}\n        {detail}")


def main():
    # Sécurité : si une API répond déjà, on s'arrête (elle fausserait le test)
    try:
        appeler("GET", "/etat")
        print("Une API tourne déjà sur le port 8000. Arrêtez-la avant de lancer ce test.")
        return 1
    except OSError:
        pass

    variables = dict(os.environ, PYTHONUTF8="1", DUREE_CRISE_SECONDES="180")
    dossier_logs = tempfile.mkdtemp(prefix="test_reinit_")
    print(f"Journaux de l'API et du simulateur : {dossier_logs}\n")

    api = simulateur = None
    commandes = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)   # pour allumer des pompes à la main
    try:
        api = lancer("api", ["-m", "uvicorn", "api:app", "--port", "8000"], variables, dossier_logs)
        for _ in range(30):                       # attend que l'API réponde (30 s maximum)
            try:
                appeler("GET", "/etat")
                break
            except OSError:
                time.sleep(1)
        else:
            print("L'API ne démarre pas.")
            return 1
        simulateur = lancer("simulateur", ["simulateur.py"], variables, dossier_logs)
        time.sleep(5)
        commandes.connect("localhost", 1883)
        commandes.loop_start()

        # ------------------------------------------------------------ A. fonctionnement normal
        # On allume la pompe de la laitue et de la pomme de terre : l'API les éteint toute seule un peu plus tard
        commandes.publish("spacefarm/zone1/cmd/pompe", "ON")
        commandes.publish("spacefarm/zone2/cmd/pompe", "ON")
        time.sleep(12)
        avant = photo()
        verifier("A0. avant : la ferme a de l'activité (eau pompée, réservoir entamé)",
                 avant[0]["consommation_totale_litres"] > 0 and avant[0]["reservoir_litres"] < 200, resume(*avant))
        appeler("POST", "/reinitialiser")
        time.sleep(6)
        apres = photo()
        verifier("A1. après réinitialisation (mode normal) : tout est à zéro", est_a_zero(*apres), resume(*apres))

        # ------------------------------------------------------------ B. pendant une fuite
        appeler("POST", "/simulation/fuite?etat=ON")
        time.sleep(8)
        en_fuite = photo()
        verifier("B0. avant : la fuite est en cours et détectée",
                 en_fuite[0]["fuite_simulee"] is True and en_fuite[0]["reservoir_litres"] < 199
                 and any(a["niveau"] == "critique" and "Fuite" in a["message"] for a in en_fuite[2]), resume(*en_fuite))
        appeler("POST", "/reinitialiser")
        time.sleep(6)
        apres = photo()
        niveau = apres[0]["reservoir_litres"]
        verifier("B1. après réinitialisation (pendant une fuite) : tout est à zéro", est_a_zero(*apres), resume(*apres))
        time.sleep(8)
        plus_tard = photo()
        verifier("B2. la fuite est bien arrêtée : le réservoir ne baisse plus, aucune alerte ne réapparaît",
                 plus_tard[0]["reservoir_litres"] == niveau and plus_tard[2] == [] and plus_tard[0]["fuite_simulee"] is False,
                 f"réservoir {niveau} -> {plus_tard[0]['reservoir_litres']} L en 8 s | alertes {len(plus_tard[2])}")

        # ------------------------------------------------------------ C. pendant une crise
        appeler("POST", "/crise/activer")
        time.sleep(8)
        en_crise = photo()
        verifier("C0. avant : la crise est en cours, recyclage coupé",
                 en_crise[1]["actif"] is True and en_crise[0]["mode"] == "crise" and en_crise[0]["recyclage_actif"] is False,
                 resume(*en_crise) + f" | budget {en_crise[1]['budget_total_litres']} L")
        appeler("POST", "/reinitialiser")
        time.sleep(6)
        apres = photo()
        verifier("C1. après réinitialisation (pendant une crise) : tout est à zéro", est_a_zero(*apres), resume(*apres))
        time.sleep(8)
        plus_tard = photo()
        verifier("C2. huit secondes plus tard : toujours propre (pas d'alerte tardive, pas de crise fantôme)",
                 plus_tard[2] == [] and plus_tard[1]["actif"] is False and plus_tard[0]["recyclage_actif"] is True,
                 resume(*plus_tard))

        # ------------------------------------------------------------ D. préréglage "démo de crise"
        appeler("POST", "/preparer-demo-crise")
        time.sleep(6)
        prete = photo()
        zones = list(prete[0]["zones"].values())
        attendues = [59, 47, 40]   # humidite_demo_crise de zones.json ; 6 s d'évaporation = environ 3 tours (1 à 1,5 point)
        humidites_ok = all(a - 5 <= z["humidite"] <= a for a, z in zip(attendues, zones))
        # Les humidités de la laitue (59 %) et de la pomme de terre (47 %) sont SOUS leurs seuils d'arrosage normaux
        # (60 % et 55 %) : sans la suspension de l'arrosage normal, leurs pompes seraient déjà en marche.
        pause_ok = all(z["pompe"] == "OFF" for z in zones) and prete[0]["demo_crise_prete"] is True
        verifier("D1. « Préparer la démo de crise » : humidités proches des seuils de survie, arrosage normal suspendu",
                 humidites_ok and pause_ok and prete[0]["consommation_totale_litres"] == 0 and prete[2] == [],
                 resume(*prete) + f" | démo prête {prete[0]['demo_crise_prete']} ({prete[0]['demo_crise_secondes_restantes']} s)")
        appeler("POST", "/reinitialiser")
        time.sleep(6)
        apres = photo()
        verifier("D2. la réinitialisation NORMALE est inchangée : humidités de départ (70 %), suspension levée",
                 est_a_zero(*apres) and apres[0]["demo_crise_prete"] is False, resume(*apres))
    finally:
        commandes.loop_stop()
        arreter(simulateur)
        arreter(api)

    print(f"\nRésultat : {sum(resultats)}/{len(resultats)} vérifications OK")
    return 0 if all(resultats) else 1


if __name__ == "__main__":
    sys.exit(main())
