# SpaceFarm — Horizon 2080 · Pilier 2 : FoodTech & AgriTech Spatiale

Ferme hydroponique autonome embarquée dans un vaisseau spatial, **surtout simulée** (deux vrais capteurs sur la zone 1, voir plus bas ; le reste est simulé). Le circuit fermé est simulé simplement : à chaque tour, 90 % de l'eau pompée revient dans le réservoir (la fuite, elle, est perdue). Trois cultures se partagent un réservoir de 200 L : tomate et pomme de terre (vitales), basilic (non vitale).
Scénario de crise : le recyclage de l'eau est contaminé donc coupé, il faut tenir **48 h** (simulées, soit 8 min réelles) avec **40 %** de l'eau normalement consommée.

## Architecture

```
Simulateur (Python) <--MQTT--> Broker Mosquitto <--MQTT--> API FastAPI <--HTTP, 2 s--> Dashboard React
capteurs, pompes, lumière      (Docker, port 1883)         règles, alertes, crise      (Vite, port 5173)
                                                           (port 8000)
```

Les mesures et les commandes circulent sur des topics MQTT ([TOPICS.md](TOPICS.md)). L'API décide (arrosage, priorité de l'eau, crise) ; le dashboard affiche et commande.

## Prérequis et installation

Windows 10/11 avec PowerShell, [Docker Desktop](https://www.docker.com/products/docker-desktop/), Python 3.10+ (testé en 3.14), Node.js 20+ (testé en 24). Une seule fois, depuis la racine du projet :

```powershell
# 1. Broker MQTT
docker run -d --name mosquitto-workshop --restart unless-stopped -p 1883:1883 -v "${PWD}\mosquitto\workshop.conf:/mosquitto/config/mosquitto.conf:ro" eclipse-mosquitto:2.0
# 2. Python
cd spacefarm; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt; cd ..
# 3. Dashboard
cd dashboard; npm install; cd ..
```

## Lancement

```powershell
.\start.ps1 -DureeCrise 180    # démo : crise de 3 min (par défaut 480 s = 8 min)
.\start.ps1 -SansCapteur       # sans le pont du capteur réel (ESP32 non branché)
.\stop.ps1                     # tout arrêter (le broker Docker reste allumé)
```

`start.ps1` vérifie (et démarre si besoin) le broker, ouvre le simulateur, l'API, le pont du capteur réel (sauf avec `-SansCapteur`) et le dashboard, chacun dans sa fenêtre, puis affiche l'adresse du dashboard : `http://127.0.0.1:5173` sur ce PC, `http://<IP du PC>:5173` pour les autres PC.

## Capteurs réels (optionnel)

La zone 1 (Tomate) peut recevoir deux mesures de **vrais capteurs** branchés sur un ESP32, relié en USB (câble série `COM3`), au lieu du simulateur : l'humidité du sol et la température de l'air. [spacefarm/pont_capteur.py](spacefarm/pont_capteur.py) lit les mesures et les republie sur MQTT ; l'API bascule alors la zone 1 sur ces valeurs réelles (le reste — pH, luminosité, pompe — continue d'être simulé ; la température n'influence aucune règle, elle est seulement affichée). Sans mesure reçue depuis 15 s, la mesure concernée repasse automatiquement en simulée, avec une alerte — indépendamment pour l'humidité et la température. Le dashboard affiche un badge « Capteur réel » (vert) ou « Simulé » (gris) sur l'humidité, avec la valeur brute du capteur quand il est actif, et un petit repère vert sur la température quand elle est réelle.

Sans ESP32 branché, lancer avec `-SansCapteur` (sinon la fenêtre du pont affiche juste une erreur de port série, sans gêner le reste). Pour libérer le port série sans arrêter le reste de la ferme (par exemple pour téléverser un nouveau programme depuis l'IDE Arduino) : `.\pont-stop.ps1`, puis `.\pont-start.ps1` pour le relancer (détails dans [DEMO.md](DEMO.md)). Détails des topics et du format : [TOPICS.md](TOPICS.md).

## CropGuard : santé des plantes par photo (module d'un membre de l'équipe)

[cropguard/](cropguard/) est un service séparé qui analyse des photos de feuilles (dossier `cropguard/flux/`) avec un modèle entraîné, détecte des symptômes (jaunissement, taches, pourriture), et publie une santé par zone sur MQTT (`cropguard/<zone>/sante`) — l'API SpaceFarm s'y abonne et avance un peu l'arrosage d'une zone dont les feuilles sont en souffrance (voir [TOPICS.md](TOPICS.md)). Le dashboard affiche un lien « CropGuard ↗ » en haut à droite vers son propre petit tableau de bord (port 8100).

**Pas lancé automatiquement** par `start.ps1` (à lancer à part, avant ou après). Sur certains PC (politique de sécurité Windows, par exemple gérée par un établissement), scikit-learn peut être bloqué hors conteneur : dans ce cas, utiliser Docker (méthode testée) :
```powershell
cd cropguard
docker build -t spacefarm-cropguard .
docker run -d --name cropguard -p 8100:8100 spacefarm-cropguard
docker rm -f cropguard   # pour l'arrêter
```
Sinon, en Python directement (plus simple si ça fonctionne sur le PC) :
```powershell
cd cropguard
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn cropguard:app --host 0.0.0.0 --port 8100
```

- **Script bloqué** (« l'exécution de scripts est désactivée ») : `powershell -ExecutionPolicy Bypass -File .\start.ps1 -DureeCrise 180`, ou une fois pour toutes `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **Autres PC** : ouvrir les ports dans le pare-feu, en PowerShell administrateur : `New-NetFirewallRule -DisplayName "SpaceFarm 5173 et 8000" -Direction Inbound -Protocol TCP -LocalPort 5173,8000 -Action Allow -Profile Any -RemoteAddress LocalSubnet`

## Le mode crise

**Budget d'eau.** Consommation normale = eau qui compense l'évaporation des trois zones pendant la crise, avec le cycle jour/nuit normal (2 min de jour, 1 min de nuit, évaporation divisée par 2 la nuit) :
(0,4 + 0,3 + 0,5) % d'évaporation par tour ÷ 4 % d'humidité par litre = 0,30 L par tour de jour ; × 0,833 (moyenne jour/nuit) ; × 240 tours de 2 s = **60 L**. Budget = 40 % × 60 L = **24 L**. C'est 40 % de la consommation normale et non 40 % du réservoir (80 L), qui donnerait plus d'eau qu'en temps normal.

**Stratégie.**
- **Recyclage coupé** à l'activation (eau recyclée contaminée), rétabli à la fin. Le calcul du budget ne change pas : il compte l'eau *pompée*.
- **Zones non vitales sacrifiées** : pompe coupée dès l'activation et interdite pendant toute la crise (leur alerte de survie critique est normale).
- **Zones vitales au seuil de survie** : pompe ON sous `seuil_survie + 5`, OFF au-dessus de `seuil_survie + 10`, une seule pompe à la fois par ordre de priorité.
- **Éclairage réduit** : 1 min de jour, 2 min de nuit, pour freiner l'évaporation.
- **Budget jamais dépassé** : avant chaque tour de pompe, l'API vérifie qu'il reste assez d'eau, sinon elle refuse et crée une alerte.
- **Fin automatique** : retour au mode normal et alerte de bilan.

## Résultats des tests

| Test | Résultat |
|---|---|
| Crise de 8 min, avec recyclage | **4/4 critères** : budget 16,1 L sur 24,0 L (**67 %**) ; minima tomate 39,8 % (seuil 35 %) et pomme de terre 34,8 % (seuil 30 %) ; basilic jamais arrosé ; retour au mode normal après 481,0 s ; recyclage coupé puis rétabli |
| Démo de crise de 3 min, 3 essais avec de vrais clics | **4/4 critères à chaque essai** ; tomate et pomme de terre arrosées, budget 4,8 L sur 9,0 L (**53 %**), minima 39,8 % et 34,85 %, basilic rouge à 50-52 s |
| Fonctionnement normal, 10 min | réservoir à **192,8 L** à la fin (> 150 L) : perte nette de 7,2 L pour 72,2 L pompés |
| Détection de fuite | alerte critique en 0,9 à 1,5 s (limite : 30 s), calcul corrigé pour le recyclage (9 scénarios) |
| « Réinitialiser la ferme » | 12/12 : tout à zéro en mode normal, pendant une fuite et pendant une crise |
| Réservoir bas (25 %) | basilic jamais arrosé, tomate et pomme de terre arrosées ; « une pompe vitale à la fois » vérifié par scénarios contrôlés seulement |
| Dashboard (navigateur automatisé) | 1920x1080 sans défilement, 1366x768 sans chevauchement |
| Capteurs réels, humidité et température (pont simulé sur MQTT, sans ESP32) | 18/18 : bascule indépendante des deux capteurs, arrosage piloté par l'humidité réelle (normal et en crise), retour au simulé après 15 s sans message (indépendant par capteur), réinitialisation, crise et fuite inchangées |
| Réactions anticipées : chaleur et CropGuard (module d'un membre de l'équipe, MQTT simulé) | 8/8 : alerte et arrosage avancé si température ≥ 28 °C ou santé des feuilles basse, retour à la normale, messages malformés ignorés, réinitialisation |

Depuis la racine : `spacefarm\.venv\Scripts\python.exe tests\test_crise.py` (3 min ; `--duree 480 --humidite-depart 70 --attente 60` pour 8 min ; `--demo` pour la démo de crise), `... tests\test_fuite_recyclage.py` (5 s), `... tests\test_reinit.py` (2 min), `... tests\test_capteur_reel.py` (1 min, sans ESP32 : simule le pont directement sur MQTT), `... tests\test_reactions_anticipees.py` (30 s, sans CropGuard réel : simule ses messages directement sur MQTT).

## Démo en 5 étapes (détail et phrases dans [DEMO.md](DEMO.md))

| # | Étape | Ce qu'on montre |
|---|---|---|
| 1 | Fonctionnement normal | pompes qui s'allument et s'éteignent seules, alternance jour/nuit |
| 2 | Fuite détectée | bouton « Simuler une fuite » : alerte critique en quelques secondes |
| 3 | Arrêt de la fuite | alerte « retour à la normale », le bouton reste correct au rechargement |
| 4 | Crise lancée | page orange, compte à rebours, pompes de survie, budget qui se remplit, zone non vitale sacrifiée |
| 5 | Fin de crise et bilan | retour automatique au mode normal, bilan de consommation |

Avant la démo : « Réinitialiser la ferme » ; à l'étape 4 : « Préparer la démo de crise » (ferme « qui a déjà souffert », pour que 3 minutes suffisent à montrer le rationnement). Captures : [dashboard/captures/](dashboard/captures/).

helloworld