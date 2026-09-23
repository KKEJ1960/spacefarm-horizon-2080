r"""
Test de l'intégration des capteurs réels (pont_capteur.py) dans l'API : humidité du sol et
température de l'air, tous deux de la zone 1.

Aucun ESP32 n'est branché sur la machine qui exécute ce test : il SIMULE donc le pont en publiant
lui-même, directement sur MQTT, des messages spacefarm/zone1/humidite_reelle et
spacefarm/zone1/temperature_reelle au même format que pont_capteur.py (voir sa fonction publier()).
Ce test ne vérifie donc PAS le port série ni le matériel (cela a été fait séparément, à la main,
avec le vrai ESP32) : seulement ce que fait l'API quand ces messages arrivent, s'arrêtent, ou se
mélangent avec une crise.

Il faut que le broker Mosquitto tourne déjà (conteneur Docker mosquitto-workshop).
Aucune autre API ni simulateur ne doit être en cours d'exécution.

Depuis la racine du projet, en PowerShell (durée : environ 1 minute) :
    spacefarm\.venv\Scripts\python.exe tests\test_capteur_reel.py

Code de sortie : 0 si toutes les vérifications passent, 1 sinon.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_SPACEFARM = RACINE / "spacefarm"
API = "http://127.0.0.1:8000"     # 127.0.0.1 plutôt que localhost : plus rapide sous Windows
ZONE = "zone1"
TOPIC_HUMIDITE = f"spacefarm/{ZONE}/humidite_reelle"
TOPIC_TEMPERATURE = f"spacefarm/{ZONE}/temperature_reelle"


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


def publier_humidite_reelle(client, valeur, brut):
    """Publie un message identique à celui de pont_capteur.py pour une ligne HUM;..."""
    message = {
        "valeur": valeur, "unite": "%", "date": datetime.now(timezone.utc).isoformat(),
        "source": "capteur-reel", "brut": brut,
    }
    client.publish(TOPIC_HUMIDITE, json.dumps(message))


def publier_temperature_reelle(client, valeur):
    """Publie un message identique à celui de pont_capteur.py pour une ligne AIR;... (pas de "brut")."""
    message = {
        "valeur": valeur, "unite": "°C", "date": datetime.now(timezone.utc).isoformat(),
        "source": "capteur-reel",
    }
    client.publish(TOPIC_TEMPERATURE, json.dumps(message))


def attendre(condition, timeout_s, pas=0.5):
    """Interroge GET /etat jusqu'à ce que condition(etat) soit vraie, ou jusqu'au délai."""
    limite = time.time() + timeout_s
    while time.time() < limite:
        etat = appeler("GET", "/etat")
        if condition(etat):
            return True, etat
        time.sleep(pas)
    return False, appeler("GET", "/etat")


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
    dossier_logs = tempfile.mkdtemp(prefix="test_capteur_reel_")
    print(f"Journaux de l'API et du simulateur : {dossier_logs}")
    print("NOTE : aucun ESP32 branché ici -> ce test simule le pont en publiant directement sur MQTT.\n"
          "Le port série lui-même a été vérifié séparément, à la main, avec le vrai matériel.\n")

    api = simulateur = None
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        api = lancer("api", ["-m", "uvicorn", "api:app", "--port", "8000"], variables, dossier_logs)
        for _ in range(30):
            try:
                appeler("GET", "/etat")
                break
            except OSError:
                time.sleep(1)
        else:
            print("L'API ne démarre pas.")
            return 1
        simulateur = lancer("simulateur", ["simulateur.py"], variables, dossier_logs)
        time.sleep(4)
        client.connect("localhost", 1883)
        client.loop_start()

        # ------------------------------------------------------------ 1. Sans le pont
        etat = appeler("GET", "/etat")
        z1 = etat["zones"][ZONE]
        verifier("1. Sans le pont : zone1 simulée (humidité et température), pas de valeur brute",
                 z1["source_humidite"] == "simulee" and z1["humidite_brute"] is None
                 and z1["source_temperature"] == "simulee",
                 f"humidité : {z1['source_humidite']} | température : {z1['source_temperature']}")

        # ------------------------------------------------------------ 2. Avec le pont (humidité seule d'abord)
        publier_humidite_reelle(client, 42.5, 380)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["source_humidite"] == "capteur-reel", 5)
        z1 = etat["zones"][ZONE]
        verifier("2. Avec le pont : zone1 bascule sur le capteur réel d'humidité",
                 ok and z1["humidite"] == 42.5 and z1["humidite_brute"] == 380,
                 f"source={z1['source_humidite']} humidité={z1['humidite']} brut={z1['humidite_brute']}")
        alertes = appeler("GET", "/alertes")
        verifier("2b. Une alerte « capteur d'humidité réel connecté » a été créée",
                 any("Capteur d'humidité réel connecté" in a["message"] for a in alertes), f"{len(alertes)} alerte(s)")
        verifier("2c. La température, elle, reste simulée : les deux capteurs sont indépendants",
                 z1["source_temperature"] == "simulee", f"source_temperature={z1['source_temperature']}")

        # On republie régulièrement (comme le vrai pont, environ toutes les 2 s), avec une valeur basse
        # (sous le seuil de survie 35 %), pour vérifier que l'arrosage réagit à la valeur RÉELLE.
        for valeur, brut in [(30.0, 260), (28.0, 240), (26.0, 220)]:
            publier_humidite_reelle(client, valeur, brut)
            time.sleep(2.2)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["pompe"] == "ON", 8)
        alertes = appeler("GET", "/alertes")
        verifier("2d. Humidité réelle basse (26 %, sous 35 %) : la pompe zone1 démarre",
                 ok, f"pompe={etat['zones'][ZONE]['pompe']} humidité={etat['zones'][ZONE]['humidite']}")
        verifier("2e. Alerte « EN DANGER » créée à partir de la valeur RÉELLE",
                 any(a["zone"] == ZONE and "seuil de survie" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")

        # On remonte l'humidité (comme replonger la fourche dans l'eau) : la pompe doit s'arrêter
        for valeur, brut in [(50.0, 430), (65.0, 520), (78.0, 610)]:
            publier_humidite_reelle(client, valeur, brut)
            time.sleep(2.2)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["pompe"] == "OFF", 8)
        verifier("2f. Humidité réelle remontée (78 %) : la pompe zone1 s'arrête",
                 ok, f"pompe={etat['zones'][ZONE]['pompe']} humidité={etat['zones'][ZONE]['humidite']}")

        # ------------------------------------------------------------ 3. Le capteur de température se branche à son tour
        publier_temperature_reelle(client, 25.8)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["source_temperature"] == "capteur-reel", 5)
        z1 = etat["zones"][ZONE]
        verifier("3. Le capteur de température bascule aussi, sans toucher à l'humidité",
                 ok and z1["temperature"] == 25.8 and z1["source_humidite"] == "capteur-reel",
                 f"température={z1['temperature']} source_temperature={z1['source_temperature']} source_humidite={z1['source_humidite']}")
        alertes = appeler("GET", "/alertes")
        verifier("3b. Une alerte « capteur de température réel connecté » a été créée",
                 any("Capteur de température réel connecté" in a["message"] for a in alertes), f"{len(alertes)} alerte(s)")

        # Doigt posé sur le capteur (essai réel de l'utilisateur : 25.8 -> 26.5 °C)
        publier_temperature_reelle(client, 26.5)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["temperature"] == 26.5, 5)
        verifier("3c. La température réelle suit un changement (25.8 -> 26.5 °C, essai « doigt sur le capteur »)",
                 ok, f"température={etat['zones'][ZONE]['temperature']}")

        # ------------------------------------------------------------ 4. Pont arrêté en cours de route : les deux capteurs
        for valeur, brut in [(70.0, 590)]:
            publier_humidite_reelle(client, valeur, brut)   # dernière mesure d'humidité avant le silence
        debut_silence = time.time()
        ok, etat = attendre(
            lambda e: e["zones"][ZONE]["source_humidite"] == "simulee" and e["zones"][ZONE]["source_temperature"] == "simulee",
            20,
        )
        duree = time.time() - debut_silence
        alertes = appeler("GET", "/alertes")
        verifier("4. Pont arrêté : les deux mesures repassent en simulé au bout de ~15 s",
                 ok and 13 <= duree <= 19, f"retour au simulé après {duree:.1f} s")
        verifier("4b. Alertes « capteur réel silencieux » créées pour l'humidité ET la température",
                 any("Capteur d'humidité réel silencieux" in a["message"] for a in alertes)
                 and any("Capteur de température réel silencieux" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")

        # ------------------------------------------------------------ 5. Crise et fuite fonctionnent toujours
        appeler("POST", "/reinitialiser")
        time.sleep(3)
        appeler("POST", "/crise/activer")
        time.sleep(2)
        crise = appeler("GET", "/crise")
        verifier("5a. La crise s'active toujours normalement", crise["actif"] is True,
                 f"budget {crise['budget_total_litres']} L")

        # Pendant la crise, le capteur réel doit continuer à piloter la zone 1, avec le seuil DE CRISE
        # (seuil_survie 35 + 5 = 40), pas le seuil normal (60). La température réelle doit aussi
        # continuer de fonctionner pendant la crise (elle ne pilote aucune règle, mais ne doit pas planter).
        publier_humidite_reelle(client, 33.0, 300)
        publier_temperature_reelle(client, 24.0)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["pompe"] == "ON", 6)
        verifier("5b. En crise, le capteur réel pilote la pompe zone1 avec le seuil de crise",
                 ok, f"pompe={etat['zones'][ZONE]['pompe']} (humidité réelle envoyée : 33.0 %)")
        verifier("5c. La température réelle est aussi prise en compte pendant la crise",
                 etat["zones"][ZONE]["source_temperature"] == "capteur-reel" and etat["zones"][ZONE]["temperature"] == 24.0,
                 f"source_temperature={etat['zones'][ZONE]['source_temperature']} température={etat['zones'][ZONE]['temperature']}")

        appeler("POST", "/crise/desactiver")
        time.sleep(2)
        crise = appeler("GET", "/crise")
        verifier("5d. La crise se termine toujours normalement", crise["actif"] is False,
                 f"bilan {crise['bilan']}")

        appeler("POST", "/simulation/fuite?etat=ON")
        time.sleep(6)
        alertes = appeler("GET", "/alertes")
        verifier("5e. La détection de fuite fonctionne toujours",
                 any(a["niveau"] == "critique" and "Fuite" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")
        appeler("POST", "/simulation/fuite?etat=OFF")

        # ------------------------------------------------------------ 6. Réinitialiser remet les deux capteurs à zéro
        appeler("POST", "/reinitialiser")
        time.sleep(3)
        etat = appeler("GET", "/etat")
        z1 = etat["zones"][ZONE]
        verifier("6. Réinitialiser la ferme remet aussi la zone 1 en humidité ET température simulées",
                 z1["source_humidite"] == "simulee" and z1["humidite_brute"] is None
                 and z1["source_temperature"] == "simulee",
                 str(z1))

    finally:
        client.loop_stop()
        arreter(simulateur)
        arreter(api)

    print(f"\nRésultat : {sum(resultats)}/{len(resultats)} vérifications OK")
    return 0 if all(resultats) else 1


if __name__ == "__main__":
    sys.exit(main())
