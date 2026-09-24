r"""
Test des réactions anticipées ajoutées par un membre de l'équipe : arrosage un peu avancé quand
il fait chaud (température), et quand CropGuard signale une plante en souffrance (santé des
feuilles, publiée sur cropguard/<zone>/sante). Aucun ESP32 ni CropGuard réel nécessaire : ce test
simule les deux en publiant directement sur MQTT.

Il faut que le broker Mosquitto tourne déjà (conteneur Docker mosquitto-workshop).
Aucune autre API ni simulateur ne doit être en cours d'exécution.

Depuis la racine du projet, en PowerShell (durée : environ 30 secondes) :
    spacefarm\.venv\Scripts\python.exe tests\test_reactions_anticipees.py

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
API = "http://127.0.0.1:8000"
ZONE = "zone2"   # zone simulée (pas zone1, qui peut avoir un vrai capteur branché) : plus simple à isoler


def appeler(methode, chemin):
    requete = urllib.request.Request(API + chemin, method=methode)
    with urllib.request.urlopen(requete, timeout=5) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def lancer(nom, arguments, variables, dossier_logs):
    log = open(Path(dossier_logs) / f"{nom}.log", "w", encoding="utf-8")
    return subprocess.Popen([sys.executable] + arguments, cwd=DOSSIER_SPACEFARM, env=variables,
                            stdout=log, stderr=subprocess.STDOUT)


def arreter(processus):
    if processus is None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(processus.pid), "/T", "/F"], capture_output=True)
    else:
        processus.terminate()


def publier_sante(client, zone_id, valeur):
    """Publie comme le ferait cropguard.py."""
    message = {"valeur": valeur, "unite": "%", "date": datetime.now(timezone.utc).isoformat()}
    client.publish(f"cropguard/{zone_id}/sante", json.dumps(message))


def attendre(condition, timeout_s, pas=0.5):
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
    try:
        appeler("GET", "/etat")
        print("Une API tourne déjà sur le port 8000. Arrêtez-la avant de lancer ce test.")
        return 1
    except OSError:
        pass

    variables = dict(os.environ, PYTHONUTF8="1", DUREE_CRISE_SECONDES="180",
                      HUMIDITE_DEPART="70")
    dossier_logs = tempfile.mkdtemp(prefix="test_reactions_")
    print(f"Journaux de l'API et du simulateur : {dossier_logs}\n")

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

        # ------------------------------------------------------------ 1. Chaleur : alerte + seuil avancé
        etat = appeler("GET", "/etat")
        verifier("1. Au départ (pas chaud) : pas d'alerte de chaleur",
                 not any("température élevée" in a["message"] for a in appeler("GET", "/alertes")),
                 "aucune alerte de chaleur au départ")

        # On force la température (simulée) au-dessus du seuil directement sur le topic du simulateur,
        # comme le ferait un vrai capteur ou le simulateur lui-même par forte chaleur.
        message = {"valeur": 29.5, "unite": "°C", "date": datetime.now(timezone.utc).isoformat()}
        client.publish(f"spacefarm/{ZONE}/temperature", json.dumps(message))
        ok, etat = attendre(lambda e: e["zones"][ZONE]["temperature"] == 29.5, 5)
        verifier("2. La température forcée est bien prise en compte", ok, f"temperature={etat['zones'][ZONE]['temperature']}")
        alertes = appeler("GET", "/alertes")
        verifier("3. Alerte de chaleur créée (température ≥ 28°C)",
                 any(a["zone"] == ZONE and "température élevée" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")

        # ------------------------------------------------------------ 4. CropGuard : plante en souffrance
        publier_sante(client, ZONE, 25.0)   # sous SEUIL_SANTE_CRITIQUE (40) : "malade"
        ok, etat = attendre(lambda e: e["zones"][ZONE]["sante_plante"] == 25.0, 5)
        verifier("4. La santé publiée par CropGuard est bien reçue", ok, f"sante_plante={etat['zones'][ZONE]['sante_plante']}")
        alertes = appeler("GET", "/alertes")
        verifier("5. Alerte « en souffrance » créée (santé sous le seuil critique)",
                 any(a["zone"] == ZONE and "en souffrance" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")

        # ------------------------------------------------------------ 6. Retour à la normale : les deux alertes se lèvent
        message = {"valeur": 22.0, "unite": "°C", "date": datetime.now(timezone.utc).isoformat()}
        client.publish(f"spacefarm/{ZONE}/temperature", json.dumps(message))
        publier_sante(client, ZONE, 80.0)
        ok, etat = attendre(lambda e: e["zones"][ZONE]["temperature"] == 22.0 and e["zones"][ZONE]["sante_plante"] == 80.0, 5)
        alertes = appeler("GET", "/alertes")
        verifier("6. Retour à la normale : les deux alertes « info » sont bien créées",
                 ok and any("redescendue" in a["message"] for a in alertes) and any("remontée" in a["message"] for a in alertes),
                 f"{len(alertes)} alerte(s)")

        # ------------------------------------------------------------ 7. Sécurité : messages CropGuard malformés/inconnus ignorés
        client.publish("cropguard/zoneInconnue/sante", json.dumps({"valeur": 10.0, "unite": "%"}))
        client.publish("cropguard/alertes", json.dumps({"date": "x", "niveau": "critique", "zone": ZONE, "message": "test"}))
        client.publish(f"cropguard/{ZONE}/sante", "ceci n'est pas du JSON")
        time.sleep(2)
        etat_apres = appeler("GET", "/etat")
        verifier("7. Messages CropGuard malformés ou d'une zone inconnue : ignorés sans planter",
                 etat_apres["zones"][ZONE]["sante_plante"] == 80.0,   # inchangé, l'API tourne toujours
                 f"sante_plante toujours {etat_apres['zones'][ZONE]['sante_plante']}, API répond toujours")

        # ------------------------------------------------------------ 8. Réinitialiser efface bien sante_plante
        appeler("POST", "/reinitialiser")
        time.sleep(3)
        etat_final = appeler("GET", "/etat")
        verifier("8. Réinitialiser la ferme efface sante_plante", etat_final["zones"][ZONE]["sante_plante"] is None,
                 str(etat_final["zones"][ZONE]["sante_plante"]))

    finally:
        client.loop_stop()
        arreter(simulateur)
        arreter(api)

    print(f"\nRésultat : {sum(resultats)}/{len(resultats)} vérifications OK")
    return 0 if all(resultats) else 1


if __name__ == "__main__":
    sys.exit(main())
