# Topics MQTT — SpaceFarm

Broker : `localhost:1883` (conteneur Docker `mosquitto-workshop`, accès anonyme).
Le simulateur ([spacefarm/simulateur.py](spacefarm/simulateur.py)) publie toutes les mesures à chaque **tour** (2 s par défaut).

## Zones

Définies dans [spacefarm/zones.json](spacefarm/zones.json). `<zone>` vaut `zone1`, `zone2` ou `zone3`.

| Zone | Culture | Vitale | Priorité |
|---|---|---|---|
| `zone1` | Laitue | oui | 1 |
| `zone2` | Pomme de terre | oui | 2 |
| `zone3` | Basilic | non | 3 |

Réglages de chaque zone dans `zones.json` :

| Champ | Signification | Unité |
|---|---|---|
| `nom` | nom de la culture | — |
| `vitale` | culture indispensable (`true`) ou non (`false`) | — |
| `priorite` | 1 = servie en premier | — |
| `seuil_arrosage` | sous cette humidité, il faut arroser | % |
| `seuil_survie` | sous cette humidité, la culture est en danger | % |
| `evaporation` | humidité perdue à chaque tour (moitié moins si lumière OFF) | % par tour |
| `debit_pompe` | eau prélevée dans le réservoir à chaque tour, pompe ON | L par tour |

Le fichier contient aussi `reservoir_capacite_litres` (capacité du réservoir, sert à calculer les pourcentages), `reservoir_litres` (niveau de départ du simulateur) `humidite_par_litre` (% d'humidité gagnés par litre d'eau pompé, lu par le simulateur et par l'API pour le budget de crise) et `taux_recyclage` (part de l'eau pompée qui revient dans le réservoir à chaque tour : 0,9 = 90 %, lu par le simulateur et par l'API pour détecter les fuites). Chaque zone a aussi `humidite_demo_crise` : son humidité de départ après « Préparer la démo de crise » (59 % laitue, 47 % pomme de terre, 40 % basilic).

## Mesures (publiées par le simulateur)

Format de tous les messages : `{"valeur": ..., "unite": "...", "date": "..."}` (date ISO 8601, UTC).

| Topic | Valeur | Unité | Exemple |
|---|---|---|---|
| `spacefarm/<zone>/humidite` | nombre | `%` | `{"valeur": 70.1, "unite": "%", "date": "..."}` |
| `spacefarm/<zone>/temperature` | nombre | `°C` | `{"valeur": 22.4, "unite": "°C", "date": "..."}` |
| `spacefarm/<zone>/ph` | nombre | `pH` | `{"valeur": 6.02, "unite": "pH", "date": "..."}` |
| `spacefarm/<zone>/luminosite` | nombre (0 si lumière OFF) | `lux` | `{"valeur": 12277, "unite": "lux", "date": "..."}` |
| `spacefarm/<zone>/pompe` | `"ON"` ou `"OFF"` | (vide) | `{"valeur": "ON", "unite": "", "date": "..."}` |
| `spacefarm/reservoir/niveau` | nombre, réservoir commun (90 % de l'eau pompée y revient quand le recyclage est actif) | `L` | `{"valeur": 199.4, "unite": "L", "date": "..."}` |

## Commandes (écoutées par le simulateur)

Le message est du **texte simple** : `ON` ou `OFF` (pas de JSON).

| Topic | Effet |
|---|---|
| `spacefarm/<zone>/cmd/pompe` | `ON` : à chaque tour, le réservoir baisse de `debit_pompe` et l'humidité de la zone remonte. `OFF` : arrêt. Réservoir vide : la pompe est forcée à `OFF`. |
| `spacefarm/<zone>/cmd/lumiere` | `ON` / `OFF` : allume ou éteint l'éclairage de la zone. Éteinte, la luminosité vaut 0 et l'évaporation est divisée par 2. |
| `spacefarm/simulation/fuite` | `ON` : fuite simulée, le réservoir perd **1 L de plus par tour**. `OFF` : fin de la fuite. Le simulateur ne publie pas l'état de la fuite : c'est à l'API de la détecter. L'API mémorise seulement le dernier ordre (envoyé par elle ou reçu ici) et l'expose dans `GET /etat` (`fuite_simulee`). |
| `spacefarm/recyclage` | `ON` (par défaut) : à chaque tour, **90 %** de l'eau pompée revient dans le réservoir. `OFF` : plus aucun retour d'eau. Publié par l'API (message **conservé** par le broker, comme `spacefarm/mode`) : `OFF` à l'activation d'une crise, `ON` à sa fin (automatique ou manuelle) et à chaque réinitialisation. L'API mémorise l'état et l'expose dans `GET /etat` (`recyclage_actif`). |
| `spacefarm/simulation/reinitialiser` | n'importe quel message : au début de son prochain tour (moins de 2 s), le simulateur remet le réservoir à son niveau de départ, les humidités, températures et pH à leur valeur de départ, éteint les pompes, arrête la fuite et rétablit le recyclage. La lumière n'est pas touchée (elle suit le cycle jour/nuit de l'API). Publié par l'API via `POST /reinitialiser` (message `ON`) ou `POST /preparer-demo-crise` (message `DEMO` : les humidités repartent des valeurs `humidite_demo_crise` de `zones.json`). |

### Recyclage de l'eau (circuit fermé)

À chaque tour, le simulateur : (1) retire du réservoir l'eau pompée par les zones, (2) **ajoute 90 % de cette eau** si le recyclage est actif, sans jamais dépasser la capacité du réservoir, (3) retire ensuite la fuite simulée. La fuite est donc **perdue** : elle n'est jamais recyclée. Le budget de crise et son calcul ne changent pas : l'eau « consommée » par les cultures reste l'eau pompée. L'API tient compte du recyclage pour détecter les fuites : la baisse attendue du réservoir vaut 10 % du débit des pompes en marche (100 % si le recyclage est coupé).

## Mode (publié par l'API)

| Topic | Contenu |
|---|---|
| `spacefarm/mode` | `{"valeur": "normal" ou "crise", "unite": "", "date": "..."}`. Message **conservé** par le broker (retain) : un nouvel abonné reçoit tout de suite le mode actuel. L'API le remet à `normal` à chaque démarrage. |

## Alertes (publiées par l'API, [spacefarm/api.py](spacefarm/api.py))

| Topic | Contenu |
|---|---|
| `spacefarm/alertes` | une alerte par message, **sans** le format `valeur/unite` : `{"date": "...", "niveau": "critique", "zone": "zone1", "message": "..."}` |

- `niveau` : `info` (dont les « retour à la normale »), `attention` ou `critique`.
- `zone` : `zone1`, `zone2`, `zone3`, `reservoir` (réservoir et fuite) ou `crise` (début, budget à 50 % / 90 %, fin de crise avec bilan).
- Une alerte n'est créée qu'au **changement d'état** d'un problème, pas à chaque tour.

| Problème | Niveau |
|---|---|
| humidité d'une zone sous `seuil_survie` | `critique` |
| réservoir sous 30 % | `attention` |
| réservoir sous 10 % | `critique` |
| le réservoir baisse plus vite que ce que les pompes en marche expliquent (tolérance 0,5 L par tour) | `critique` |

## API HTTP (mêmes données pour le dashboard)

Lancer : `python -m uvicorn api:app --port 8000` depuis `spacefarm/`. En PowerShell, utiliser `127.0.0.1` plutôt que `localhost` (plus rapide).

| Route | Rôle |
|---|---|
| `GET /etat` | dernier état de chaque zone et du réservoir, avec `consommation_litres` par zone, `consommation_totale_litres`, `fuite_simulee`, `recyclage_actif`, `demo_crise_prete` et `demo_crise_secondes_restantes` |
| `GET /alertes` | liste des alertes (200 dernières, de la plus ancienne à la plus récente) |
| `POST /simulation/fuite?etat=ON` ou `OFF` | déclenche ou arrête la fuite simulée (publie sur `spacefarm/simulation/fuite`) |
| `GET /crise` | `actif`, `temps_restant_secondes`, `budget_total_litres`, `budget_consomme_litres`, `budget_restant_litres`, `zones_en_danger` (humidité sous `seuil_survie`), et `bilan` une fois la crise finie |
| `POST /crise/activer` | déclenche la crise (sans effet si déjà en cours) |
| `POST /crise/desactiver` | termine la crise avant l'heure (bilan « manuelle ») |
| `POST /reinitialiser` | remet la ferme à zéro pour préparer la démo : réservoir plein, humidités de départ, compteurs de consommation à zéro, alertes vidées, plus de fuite ni de crise, recyclage actif, nouveau cycle jour/nuit. Le réservoir et les humidités sont remis à zéro par le simulateur, dans les 2 secondes. |

| `POST /preparer-demo-crise` | comme `POST /reinitialiser`, mais les humidités repartent de `humidite_demo_crise` (laitue 59 %, pomme de terre 47 %, basilic 40 %) : une ferme qui a « déjà souffert ». L'arrosage automatique **normal** est suspendu jusqu'à `POST /crise/activer`, 45 s au maximum (`demo_crise_prete` vaut `true` pendant ce temps) |

### Préréglage « démo de crise »

Sur 3 minutes de crise depuis un fonctionnement normal, les zones vitales n'ont pas toujours besoin d'eau : la laitue perd 24 points et la pomme de terre 18, alors qu'on ne les arrose que sous 40 % et 35 %. Le préréglage part donc d'humidités plus basses. Les valeurs (59 / 47 / 40) sont le meilleur compromis calculé : plus bas, la crise consomme 97 à 99 % du budget ; plus haut, le rationnement devient invisible. L'arrosage normal est suspendu pendant l'attente entre « Préparer » et « Activer la crise », sinon il remonterait aussitôt les zones. Au-delà de 45 s d'attente, il reprend tout seul.

### Mode crise

- **Durée :** 480 s (48 h simulées = 8 min réelles), modifiable avec la variable d'environnement `DUREE_CRISE_SECONDES` au lancement de l'API. Retour automatique au mode normal à la fin.
- **Budget :** 40 % de la consommation **normale** sur la durée de la crise (eau qui compense l'évaporation de toutes les zones, cycle jour/nuit normal), pas 40 % du réservoir. Avec les valeurs actuelles : 60 L normaux, budget 24 L pour 480 s. Jamais dépassé : avant chaque `ON` (et à chaque tour de pompe), l'API vérifie qu'il reste de quoi pomper un tour, sinon elle refuse et crée une alerte.
- **Recyclage :** coupé à l'activation (l'eau recyclée est contaminée), rétabli à la fin de la crise, automatique ou manuelle.
- **Zones non vitales :** pompe coupée dès l'activation et interdite pendant toute la crise (leur alerte de survie critique est normale).
- **Zones vitales :** pompe `ON` sous `seuil_survie + 5`, `OFF` au-dessus de `seuil_survie + 10`, une seule pompe à la fois par ordre de priorité.
- **Éclairage :** cycle de crise 1 min de jour / 2 min de nuit (au lieu de 2 min / 1 min).
- **Variable du simulateur :** `HUMIDITE_DEPART` (70 par défaut) règle l'humidité de départ des zones, utile pour les tests courts.

## Écouter et commander depuis PowerShell

```powershell
# Tout écouter
docker run --rm eclipse-mosquitto:2.0 mosquitto_sub -h host.docker.internal -p 1883 -t "spacefarm/#" -v

# Allumer la pompe de la zone 1
docker run --rm eclipse-mosquitto:2.0 mosquitto_pub -h host.docker.internal -p 1883 -t spacefarm/zone1/cmd/pompe -m ON
```
