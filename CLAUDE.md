# Horizon 2080 — Pilier 2 : FoodTech & AgriTech Spatiale

Workshop EPSI. Simulation d'une **ferme hydroponique autonome dans un vaisseau spatial**. Le circuit fermé est simulé de façon simple : à chaque tour, 90 % de l'eau pompée revient dans le réservoir (`taux_recyclage` dans `zones.json`) ; la fuite simulée n'est pas recyclée, et le recyclage est coupé pendant la crise.
Aucun matériel physique : tout est simulé.

## Échéances

- Rendu : **jeudi 24/09**
- Soutenance : **vendredi 25/09**

## Périmètre retenu

### SpaceFarm
- Capteurs simulés : humidité, température, pH, luminosité, niveau d'eau.
- Arrosage et éclairage automatiques.
- Dashboard web.

### WaterLoop
- Consommation d'eau par culture.
- Détection de fuites.
- Distribution de l'eau par priorité.

### Scénario de crise
- Contamination du recyclage de l'eau.
- Objectif : maintenir les cultures pendant **48 h** avec seulement **40 %** de l'eau disponible.

## Stack retenue

**Il n'y a pas de VM Debian** : tout tourne sur le PC Windows de l'utilisateur, commandes en **PowerShell** (5.1 : pas d'opérateur `&&`).

- Broker MQTT : Mosquitto dans Docker, conteneur `mosquitto-workshop` (image `eclipse-mosquitto:2.0`), port Windows **1883**, accès anonyme, redémarrage automatique (`--restart unless-stopped`). Config : [mosquitto/workshop.conf](mosquitto/workshop.conf), montée dans le conteneur.
- Clients MQTT (`mosquitto_pub` / `mosquitto_sub`) : non installés sur Windows, on les lance via Docker avec `-h host.docker.internal -p 1883` (voir [TOPICS.md](TOPICS.md)).
- Python 3.14 : environnement virtuel `spacefarm/.venv`, paquets dans `spacefarm/requirements.txt` (`paho-mqtt`, `fastapi`, `uvicorn`).
- Dashboard : React + Vite dans `dashboard/` (Node 24), interroge l'API toutes les 2 s. Captures d'écran dans `dashboard/captures/`.
- Documentation des topics MQTT et des routes de l'API : [TOPICS.md](TOPICS.md). Test de la crise : `tests/test_crise.py`.
- `mosquitto/install.sh` et `mosquitto/test.sh` : option pour une éventuelle VM Debian, non utilisés ni testés ici.

Commande de création du broker :

```powershell
docker run -d --name mosquitto-workshop --restart unless-stopped -p 1883:1883 -v "C:\Users\kouas\OneDrive\Bureau\projetEPSI2\mosquitto\workshop.conf:/mosquitto/config/mosquitto.conf:ro" eclipse-mosquitto:2.0
```

## Lancer le projet (depuis la racine, en PowerShell)

```powershell
.\start.ps1 -DureeCrise 180   # broker vérifié, puis simulateur + API (0.0.0.0) + dashboard, chacun dans sa fenêtre
.\stop.ps1                    # arrête les trois (le broker Docker reste allumé)
```

Si Windows bloque le script : `powershell -ExecutionPolicy Bypass -File .\start.ps1 -DureeCrise 180`. Les `.ps1` doivent rester en UTF-8 **avec BOM** (sinon PowerShell 5.1 casse les accents). Documents de rendu : [README.md](README.md) et [DEMO.md](DEMO.md).

Piège PowerShell 5.1 : utiliser `127.0.0.1` et non `localhost` dans les commandes (`Invoke-RestMethod http://127.0.0.1:8000/etat`), sinon chaque appel est très lent.

## Contraintes d'équipe

Équipe débutante. Le code doit être :
- simple ;
- commenté (en français) ;
- lisible ;
- sans architecture compliquée.

## Règles de travail pour Claude

1. **Avant de coder chaque étape**, expliquer le principe en quelques lignes.
2. **Travailler étape par étape** et attendre la validation de l'utilisateur avant de passer à la suivante.
3. **À la fin de chaque étape**, donner une commande de test précise et le résultat attendu.
