r"""
Test du scénario de crise "contamination du système de recyclage".

Ce script fait tout seul :
  1. il lance l'API et le simulateur (avec une durée de crise réduite) ;
  2. il active la crise (POST /crise/activer) ;
  3. il affiche l'évolution toutes les 20 secondes ;
  4. quand la crise est finie, il vérifie 4 critères.

Il faut que le broker Mosquitto tourne déjà (conteneur Docker mosquitto-workshop).
Aucune autre API ni simulateur ne doit être en cours d'exécution.

Depuis la RACINE du projet, en PowerShell :

  Test court (crise de 3 minutes, zones qui partent de 50 % d'humidité) :
    spacefarm\.venv\Scripts\python.exe tests\test_crise.py

  Vraie crise de 8 minutes (zones qui partent de 70 %, crise déclenchée après 60 s de
  fonctionnement normal) :
    spacefarm\.venv\Scripts\python.exe tests\test_crise.py --duree 480 --humidite-depart 70 --attente 60

  Essai de la démo de crise (« Préparer la démo de crise », 10 s, « Activer la crise » ; 3 critères en plus) :
    spacefarm\.venv\Scripts\python.exe tests\test_crise.py --demo

  Même essai, mais avec de vrais clics sur le dashboard : lancer start.ps1 -DureeCrise 180, puis
    spacefarm\.venv\Scripts\python.exe tests\test_crise.py --demo --externe
  et cliquer sur « Préparer la démo de crise », attendre 10 s, cliquer sur « Activer la crise ».

Code de sortie : 0 si les 4 critères (et, avec --demo, les 3 critères de la démo) sont respectés, 1 sinon.
"""

import argparse
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

# Accents lisibles et affichage immédiat, même si la sortie est redirigée vers un fichier
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_SPACEFARM = RACINE / "spacefarm"
API = "http://127.0.0.1:8000"     # 127.0.0.1 plutôt que localhost : plus rapide sous Windows
PAS_AFFICHAGE = 20                # une ligne du tableau toutes les 20 secondes
TOLERANCE_APPLICATION = 1.0       # secondes : une commande OFF met un instant à agir (voir critère 3)

with open(DOSSIER_SPACEFARM / "zones.json", encoding="utf-8") as fichier:
    ZONES = json.load(fichier)["zones"]
NOMS_ZONES = sorted(ZONES)                                   # ["zone1", "zone2", "zone3"]
VITALES = [z for z in NOMS_ZONES if ZONES[z]["vitale"]]
NON_VITALES = [z for z in NOMS_ZONES if not ZONES[z]["vitale"]]

# Tous les messages MQTT reçus pendant le test : (heure, topic, valeur)
enregistrements = []


def on_message(client, userdata, msg):
    """Enregistre chaque mesure reçue (les messages sans "valeur", comme les alertes, sont ignorés)."""
    if msg.topic == "spacefarm/recyclage":   # ordre de recyclage : texte simple ON/OFF, pas de JSON
        enregistrements.append((time.time(), msg.topic, msg.payload.decode().strip().upper()))
        return
    try:
        valeur = json.loads(msg.payload)["valeur"]
    except (ValueError, KeyError, TypeError):
        return
    enregistrements.append((time.time(), msg.topic, valeur))


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


def formater_zone(zone, tours_on):
    """Ex. ' 45.3 ON   4' : humidité, état de la pompe, tours où elle a tourné depuis la ligne précédente."""
    if zone["humidite"] is None:
        return "  -    -   - "
    return f"{zone['humidite']:5.1f} {zone['pompe'] or '-':<3} {tours_on:>3}"


def compter_tours_on(depuis):
    """Nombre de tours où la pompe de chaque zone a tourné depuis l'heure 'depuis' (1 tour = 2 s)."""
    compte = {zone: 0 for zone in NOMS_ZONES}
    for t, topic, valeur in list(enregistrements):
        morceaux = topic.split("/")
        if t > depuis and valeur == "ON" and len(morceaux) == 3 and morceaux[2] == "pompe" and morceaux[1] in compte:
            compte[morceaux[1]] += 1
    return compte


def afficher_ligne(ecoule, etat, statut, tours_on):
    zones = etat["zones"]
    lumiere = zones[NOMS_ZONES[0]]["lumiere"] or "-"
    colonnes = " | ".join(formater_zone(zones[z], tours_on[z]) for z in NOMS_ZONES)
    recyclage = "ON" if etat["recyclage_actif"] else "OFF"
    print(f"{int(ecoule):>4} | {colonnes} | {lumiere:<7} | {recyclage:<7} | {statut['budget_restant_litres']:>6.2f} L "
          f"| {statut['temps_restant_secondes']:>5.0f} s", flush=True)


def resultat(numero, description, ok, detail):
    print(f"[{'OK' if ok else 'ECHEC'}] {numero}. {description}\n        {detail}", flush=True)
    return ok


def main():
    parseur = argparse.ArgumentParser(description="Test complet du mode crise")
    parseur.add_argument("--duree", type=int, default=180, help="durée de la crise en secondes (480 = 8 min)")
    parseur.add_argument("--humidite-depart", type=float, default=50,
                         help="humidité de départ des zones en %% (70 = valeur normale de la simulation)")
    parseur.add_argument("--attente", type=int, default=0,
                         help="secondes de fonctionnement normal avant la crise. 0 = la crise commence avant "
                              "le simulateur : les zones partent alors exactement de --humidite-depart")
    parseur.add_argument("--demo", action="store_true",
                         help="essai de la démo de crise : POST /preparer-demo-crise, attente de 10 s, puis crise. "
                              "Ajoute 3 critères : les deux zones vitales arrosées au moins une fois, budget consommé "
                              ">= 30 %%, basilic rouge avant 90 s")
    parseur.add_argument("--externe", action="store_true",
                         help="l'API et le simulateur tournent déjà (start.ps1) et c'est quelqu'un d'autre (un clic sur "
                              "le dashboard) qui lance la crise : le script attend son début et l'observe")
    args = parseur.parse_args()

    # Sécurité : sans --externe, si une API répond déjà, on s'arrête (elle fausserait le test)
    try:
        appeler("GET", "/etat")
        api_deja_la = True
    except OSError:
        api_deja_la = False
    if api_deja_la and not args.externe:
        print("Une API tourne déjà sur le port 8000. Arrêtez-la avant de lancer ce test (ou utilisez --externe).")
        return 1
    if args.externe and not api_deja_la:
        print("--externe : aucune API ne répond sur le port 8000. Lancez d'abord start.ps1.")
        return 1

    variables = dict(os.environ, PYTHONUTF8="1",
                     DUREE_CRISE_SECONDES=str(args.duree), HUMIDITE_DEPART=str(args.humidite_depart))
    dossier_logs = tempfile.mkdtemp(prefix="test_crise_")
    duree = args.duree   # durée de la crise ; en mode --externe, on la lit dans l'API
    if args.externe:
        print("Mode externe : l'API et le simulateur tournent déjà, la crise sera lancée par un clic sur le dashboard.\n")
    elif args.demo:
        print(f"Essai de la démo de crise : crise de {args.duree} s après « Préparer la démo de crise » + 10 s.")
        print(f"Journaux de l'API et du simulateur : {dossier_logs}\n")
    else:
        print(f"Crise de {args.duree} s, zones à {args.humidite_depart} % au départ, "
              f"{args.attente} s de fonctionnement normal avant la crise.")
        print(f"Journaux de l'API et du simulateur : {dossier_logs}\n")

    # On écoute tous les messages MQTT pour vérifier les critères avec des données brutes
    ecouteur = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    ecouteur.on_message = on_message
    ecouteur.connect("localhost", 1883)
    ecouteur.subscribe("spacefarm/#")
    ecouteur.loop_start()

    api = simulateur = None
    try:
        if args.externe:
            # Quelqu'un d'autre lance la crise : on attend qu'elle commence (5 minutes maximum)
            print("En attente du lancement de la crise (clic sur « Activer la crise »)...", flush=True)
            for _ in range(300):
                if appeler("GET", "/crise")["actif"]:
                    break
                time.sleep(1)
            else:
                print("La crise n'a pas été lancée : temps dépassé.")
                return 1
            # Heure exacte de l'activation = dernier message "mode = crise" reçu
            t_activation = next((t for t, topic, valeur in reversed(enregistrements)
                                 if topic == "spacefarm/mode" and valeur == "crise"), time.time())
            duree = appeler("GET", "/crise")["duree_secondes"]
        else:
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

            if args.demo:
                # Comme les deux clics du dashboard : « Préparer la démo de crise », 10 s d'attente, « Activer la crise »
                simulateur = lancer("simulateur", ["simulateur.py"], variables, dossier_logs)
                time.sleep(4)
                appeler("POST", "/preparer-demo-crise")
                time.sleep(10)
            elif args.attente > 0:
                simulateur = lancer("simulateur", ["simulateur.py"], variables, dossier_logs)
                time.sleep(args.attente)              # fonctionnement normal

            t_activation = time.time()
            appeler("POST", "/crise/activer")
            if simulateur is None:
                simulateur = lancer("simulateur", ["simulateur.py"], variables, dossier_logs)
        statut = appeler("GET", "/crise")
        print(f"Crise activée : consommation normale {statut['consommation_normale_litres']} L, "
              f"budget {statut['budget_total_litres']} L ({statut['duree_secondes']:.0f} s)\n")

        print(f"{'t(s)':>4} | " + " | ".join(f"{z:<13}" for z in NOMS_ZONES)
              + " | lumière | recycl. | budget restant | temps restant")
        print(f"{'':>4} | " + " | ".join(f"{'hum  pompe ON*':<13}" for _ in NOMS_ZONES))
        print("* ON = nombre de tours (2 s) où la pompe a tourné depuis la ligne précédente")
        print("-" * 114)

        # --- Suivi de la crise : on interroge l'API chaque seconde, on affiche toutes les 20 s ---
        prochain_affichage = 0
        derniere_ligne = t_activation
        recyclage_vu = []   # état du recyclage relevé dans GET /etat à chaque ligne du tableau : (secondes, actif)
        while True:
            ecoule = time.time() - t_activation
            statut = appeler("GET", "/crise")
            if ecoule >= prochain_affichage or not statut["actif"]:
                etat_ligne = appeler("GET", "/etat")
                recyclage_vu.append((ecoule, etat_ligne["recyclage_actif"]))
                afficher_ligne(ecoule, etat_ligne, statut, compter_tours_on(derniere_ligne))
                derniere_ligne = time.time()
                while prochain_affichage <= ecoule:
                    prochain_affichage += PAS_AFFICHAGE
            if not statut["actif"]:
                break
            if ecoule > duree + 30:
                print("La crise ne se termine pas : temps dépassé.")
                break
            time.sleep(1)

        time.sleep(2)   # laisse arriver les derniers messages MQTT
        statut = appeler("GET", "/crise")
        etat = appeler("GET", "/etat")
        alertes = appeler("GET", "/alertes")
        donnees = list(enregistrements)
    finally:
        ecouteur.loop_stop()
        arreter(simulateur)
        arreter(api)

    # --- Analyse ---
    # La fin de la crise = premier message "mode = normal" reçu après l'activation
    t_fin = next((t for t, topic, valeur in donnees
                  if topic == "spacefarm/mode" and valeur == "normal" and t > t_activation), None)
    if t_fin is None:
        print("\nAucun retour au mode normal détecté sur spacefarm/mode.")
        t_fin = time.time()
    pendant = [(t, topic, valeur) for t, topic, valeur in donnees if t_activation <= t <= t_fin]

    print("\n=== Alertes créées depuis l'activation ===")
    debut_utc = datetime.fromtimestamp(t_activation, timezone.utc)
    for alerte in alertes:
        if datetime.fromisoformat(alerte["date"]) >= debut_utc:
            heure = datetime.fromisoformat(alerte["date"]).astimezone().strftime("%H:%M:%S")
            print(f"{heure}  {alerte['niveau']:<9} {alerte['zone']:<8} {alerte['message']}")

    bilan = statut["bilan"] or {}
    print("\n=== Bilan de la crise ===")
    for cle, valeur in bilan.items():
        print(f"  {cle} : {valeur}")

    print("\n=== Vérifications ===")
    resultats = []

    # 1. Le budget n'est jamais dépassé (trois mesures indépendantes)
    total = bilan.get("budget_total_litres", 0)
    consomme_api = bilan.get("budget_consomme_litres", 999)
    consomme_mqtt = sum(ZONES[topic.split("/")[1]]["debit_pompe"] for t, topic, valeur in pendant
                        if topic.endswith("/pompe") and valeur == "ON")
    niveaux = [(t, valeur) for t, topic, valeur in donnees if topic == "spacefarm/reservoir/niveau"]
    avant = [valeur for t, valeur in niveaux if t <= t_activation]
    niveau_debut = avant[-1] if avant else next(valeur for t, valeur in niveaux if t > t_activation)
    niveau_fin = [valeur for t, valeur in niveaux if t <= t_fin][-1]
    baisse_reservoir = niveau_debut - niveau_fin
    resultats.append(resultat(
        1, "budget consommé <= budget total",
        consomme_api <= total and consomme_mqtt <= total + 1e-9 and baisse_reservoir <= total + 1e-9,
        f"budget {total} L | compté par l'API {consomme_api} L | pompes vues sur MQTT {consomme_mqtt:.2f} L "
        f"| baisse du réservoir {baisse_reservoir:.2f} L ({niveau_debut} -> {niveau_fin})"))

    # 2. Zones vitales jamais sous leur seuil de survie
    details, ok2 = [], True
    for zone in VITALES:
        valeurs = [valeur for t, topic, valeur in pendant if topic == f"spacefarm/{zone}/humidite"]
        seuil = ZONES[zone]["seuil_survie"]
        minimum = min(valeurs) if valeurs else None
        ok2 = ok2 and minimum is not None and minimum >= seuil
        details.append(f"{zone} ({ZONES[zone]['nom']}) minimum {minimum} % pour un seuil de survie de {seuil} % "
                       f"({len(valeurs)} mesures)")
    resultats.append(resultat(2, "zones vitales jamais sous leur seuil de survie", ok2, "\n        ".join(details)))

    # 3. Zones non vitales jamais arrosées (on tolère TOLERANCE_APPLICATION s après l'activation :
    #    la commande OFF envoyée à l'activation doit d'abord arriver au simulateur)
    details, ok3 = [], True
    for zone in NON_VITALES:
        allumages = [t - t_activation for t, topic, valeur in pendant
                     if topic == f"spacefarm/{zone}/pompe" and valeur == "ON"]
        tardifs = [d for d in allumages if d > TOLERANCE_APPLICATION]
        ok3 = ok3 and not tardifs
        details.append(f"{zone} ({ZONES[zone]['nom']}) : {len(tardifs)} tour(s) arrosé(s) pendant la crise"
                       f" ({len(allumages) - len(tardifs)} dans la première seconde, avant l'effet du OFF)")
    resultats.append(resultat(3, "zone(s) non vitale(s) jamais arrosée(s) pendant la crise", ok3,
                              "\n        ".join(details)))

    # 4. Retour automatique au mode normal
    duree_reelle = t_fin - t_activation
    ok4 = (not statut["actif"] and etat["mode"] == "normal" and bilan.get("origine") == "automatique"
           and abs(duree_reelle - duree) <= 5)
    resultats.append(resultat(
        4, "retour automatique au mode normal", ok4,
        f"actif={statut['actif']} | mode={etat['mode']} | fin {bilan.get('origine')} après {duree_reelle:.1f} s "
        f"(prévu {duree:.0f} s)"))

    print(f"\nRésultat : {sum(resultats)}/4 critères respectés")

    # Vérification complémentaire (hors des 4 critères) : le recyclage est coupé pendant la crise
    # (l'eau recyclée est contaminée) puis rétabli à la fin.
    ordres = [(t, valeur) for t, topic, valeur in donnees if topic == "spacefarm/recyclage"]
    pendant_crise = [valeur for t, valeur in ordres if t_activation <= t < t_fin - 0.2]   # l'"ON" publié au démarrage de l'API est avant
    apres_fin = [(t, valeur) for t, valeur in ordres if t >= t_fin - 0.2]
    vus_en_crise = [actif for secondes, actif in recyclage_vu if 2 < secondes < duree - 2]
    ok_recyclage = (
        len(pendant_crise) >= 1 and all(v == "OFF" for v in pendant_crise)          # OFF publié, jamais ON pendant la crise
        and bool(apres_fin) and apres_fin[0][1] == "ON" and apres_fin[0][0] - t_fin < 3   # ON publié à la fin
        and len(vus_en_crise) >= 1 and not any(vus_en_crise)                        # GET /etat : recyclage_actif = false
        and etat["recyclage_actif"] is True                                         # GET /etat après la crise : true
        and abs(baisse_reservoir - consomme_mqtt) <= 0.6                            # aucun recyclage : la baisse = l'eau pompée
    )
    print(f"[{'OK' if ok_recyclage else 'ECHEC'}] +. recyclage OFF pendant la crise, ON à la fin (vérification complémentaire)\n"
          f"        ordres pendant la crise : {pendant_crise} | premier ordre après la fin : "
          f"{apres_fin[0][1] if apres_fin else None} | GET /etat pendant la crise : "
          f"{'coupé' if vus_en_crise and not any(vus_en_crise) else vus_en_crise} | après la crise : "
          f"{'actif' if etat['recyclage_actif'] else 'coupé'} | baisse du réservoir {baisse_reservoir:.2f} L pour "
          f"{consomme_mqtt:.2f} L pompés", flush=True)

    # Critères de la démo de crise (--demo) : le rationnement doit être visible par le jury
    ok_demo = True
    if args.demo:
        # Nombre de cycles de pompe (allumages) de chaque zone vitale pendant la crise
        cycles = {}
        for zone in VITALES:
            etats = [valeur for t, topic, valeur in pendant if topic == f"spacefarm/{zone}/pompe"]
            cycles[zone] = sum(1 for i, v in enumerate(etats) if v == "ON" and (i == 0 or etats[i - 1] != "ON"))
        pourcent = bilan.get("budget_consomme_litres", 0) / total * 100 if total else 0
        # Moment où la zone non vitale passe sous son seuil de survie (= carte rouge)
        rouge = None
        for zone in NON_VITALES:
            sous_seuil = [t - t_activation for t, topic, valeur in pendant
                          if topic == f"spacefarm/{zone}/humidite" and valeur < ZONES[zone]["seuil_survie"]]
            if sous_seuil:
                rouge = min(sous_seuil)
        minima = {zone: min(v for t, topic, v in pendant if topic == f"spacefarm/{zone}/humidite") for zone in VITALES}
        c_ok = all(cycles[zone] >= 1 for zone in VITALES)
        b_ok = pourcent >= 30
        r_ok = rouge is not None and rouge < 90
        ok_demo = c_ok and b_ok and r_ok
        print(f"[{'OK' if c_ok else 'ECHEC'}] d1. les deux zones vitales arrosées au moins une fois en mode survie\n"
              f"        cycles de pompe : " + " | ".join(f"{ZONES[z]['nom']} {cycles[z]}" for z in VITALES))
        print(f"[{'OK' if b_ok else 'ECHEC'}] d2. budget consommé >= 30 %\n"
              f"        {bilan.get('budget_consomme_litres')} L sur {total} L = {pourcent:.1f} %")
        print(f"[{'OK' if r_ok else 'ECHEC'}] d3. la zone non vitale devient rouge avant 90 s\n"
              f"        sous son seuil de survie à {('%.0f s' % rouge) if rouge is not None else 'jamais'} de crise")
        print("ESSAI : budget {} L ({:.1f} %) | minima {} | basilic rouge à {} | cycles {}".format(
            bilan.get("budget_consomme_litres"), pourcent,
            " / ".join(f"{minima[z]}" for z in VITALES),
            ("%.0f s" % rouge) if rouge is not None else "jamais",
            " / ".join(str(cycles[z]) for z in VITALES)), flush=True)
    return 0 if all(resultats) and ok_recyclage and ok_demo else 1


if __name__ == "__main__":
    sys.exit(main())
