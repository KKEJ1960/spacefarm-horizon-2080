# DEMO — antisèche pour la soutenance (vendredi 25/09)

Une seule fenêtre à montrer : le dashboard. Durées **mesurées** :

| Partie | Durée |
|---|---|
| Préparation : lancement (12 s) + 2 minutes de fonctionnement | 2 min 14 s |
| 1. Fonctionnement normal | 1 min 40 s (90 s d'observation + 10 s pour qu'une pompe soit en marche à l'écran) |
| 2. Fuite détectée | 30 s (alerte visible 1,6 s après le clic) |
| 3. Arrêt de la fuite | 30 s (alerte de retour visible 1,6 s après le clic) |
| 4. Crise lancée : « Préparer la démo de crise », 10 s, « Activer la crise », crise | 3 min 12 s (10 s d'attente + crise de 182 s) |
| 5. Fin de crise et bilan | 30 s |
| **Total des 5 étapes** | **6 min 22 s** |

Les étapes 1, 2, 3 et 5 viennent d'une démo jouée d'un seul tenant ; l'étape 4 de 3 essais consécutifs avec le bouton « Préparer la démo de crise ». Les temps d'arrêt des étapes 1, 2, 3 et 5 sont ceux prévus ici ; seuls la crise et les délais d'apparition sont vraiment mesurés.

## Avant de commencer (10 minutes avant)

**Commande de lancement à utiliser** (PowerShell, à la racine du projet) :

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -DureeCrise 180
```

Pourquoi : Windows bloque par défaut les scripts `.ps1` sur ce PC (message « l'exécution de scripts est désactivée sur ce système »). Cette commande autorise le script pour ce seul lancement, sans changer les réglages de sécurité du PC. Pour l'arrêt, même principe : `powershell -ExecutionPolicy Bypass -File .\stop.ps1`.

**Capteur réel (zone Tomate) :** si l'ESP32 est branché sur `COM3`, la commande ci-dessus lance aussi le pont capteur dans sa propre fenêtre, sans rien à faire de plus. **S'il n'est pas branché aujourd'hui**, ajouter `-SansCapteur` : `powershell -ExecutionPolicy Bypass -File .\start.ps1 -DureeCrise 180 -SansCapteur` (sinon la fenêtre du pont affiche juste une erreur de port série, sans gêner le reste de la démo).

1. Docker Desktop est lancé.
2. Lancer la commande ci-dessus : trois fenêtres s'ouvrent, l'adresse du dashboard s'affiche (9 à 12 s).
3. Ouvrir `http://127.0.0.1:5173` sur l'écran projeté, plein écran (F11), zoom 100 %. Tout le tableau de bord tient sur un écran 1920x1080 sans défiler.
4. Cliquer sur **« Réinitialiser la ferme »** (panneau Simulation) : réservoir à 200 L, humidités de départ, alertes vidées, plus de fuite ni de crise. Les valeurs se remettent à jour en moins de 2 secondes (0,9 à 1,3 s mesuré).
5. Laisser tourner **au moins 2 minutes** : la première pompe s'allume vers 50 s, il y a donc déjà de l'activité à montrer.
6. Vérifier : badge vert « Mode normal », pastille verte « Recyclage actif », liste d'alertes vide ou presque, aucune fuite. Sinon, un nouveau clic sur « Réinitialiser la ferme » suffit (pas besoin d'arrêter ni de relancer).

## Le déroulé

### 1. Fonctionnement normal (environ 1 min 30, aucun clic)

- **Je clique :** rien, je montre avec la souris.
- **Le jury voit :** trois cartes dont les barres d'humidité descendent lentement. Quand une barre touche son repère orange « arrosage », le bandeau bleu « Pompe en marche » apparaît, l'humidité remonte d'environ 15 points, puis la pompe s'arrête seule (observé : la tomate s'allume à 62 % et s'arrête à 76 %). Le réservoir baisse à peine (198,6 L puis 197,9 L en 90 s) : 90 % de l'eau pompée y revient (pastille verte « Recyclage actif »). La luminosité alterne : environ 12 000 lux le jour (2 minutes), 0 lux la nuit (1 minute). En suivant la checklist (réinitialiser puis attendre 2 minutes), la nuit tombe juste au début de cette étape : 0 lux pendant la première minute, puis le jour revient.
- **Je dis :** « Ici la ferme tourne seule. Chaque capteur est simulé, et l'API compare l'humidité de chaque zone à son seuil d'arrosage : elle allume la pompe en dessous et l'éteint 15 points plus haut. Il n'y a personne dans la boucle. »

### 2. Fuite détectée (environ 30 s)

- **Je clique :** « Simuler une fuite (ON) ».
- **Le jury voit :** en moins de 4 secondes (1,6 s observé), une alerte rouge CRITIQUE « Fuite suspectée : le réservoir a perdu 1.0 L en un tour, les pompes n'expliquent que 0.0 L ». Le réservoir se vide plus vite, environ 1 L toutes les 2 secondes (197,9 L puis 192,7 L en 10 s) : l'eau de la fuite n'est pas recyclée. Le bouton devient plein : « Arrêter la fuite ».
- **Je dis :** « On vient de percer le circuit, sans le dire à l'API. Elle compare la baisse réelle du réservoir à ce que les pompes en marche peuvent expliquer : dès que l'écart dépasse 0,5 L par tour, alerte critique. »

### 3. Arrêt de la fuite (environ 30 s)

- **Je clique :** « Arrêter la fuite (OFF) ». Puis **F5** pour recharger la page.
- **Le jury voit :** une alerte bleue INFO « Retour à la normale… » (1,6 s après le clic). Après F5, le bouton affiche « Simuler une fuite (ON) » : l'état de la fuite vient de l'API, pas de la page. Le réservoir a perdu environ 16 L pendant ces 30 secondes de fuite (197,9 L puis 182,3 L) et ne les récupère pas.
- **Je dis :** « Une alerte n'est créée qu'au changement d'état, donc pas de doublon, et le retour à la normale est signalé. L'état de la fuite est mémorisé côté API, pas dans la page. »

### 4. Crise lancée (environ 3 min 10)

- **Je clique :** d'abord **« Préparer la démo de crise »** (panneau Simulation, à côté de « Réinitialiser la ferme »), puis, **dans les 45 secondes** (10 s dans nos essais), **« Activer la crise »**. Entre les deux, une ligne jaune orangé indique « Démo prête : lancez la crise dans les N s (l'arrosage normal est en pause) ». Le clic sur « Préparer » remet aussi le réservoir à 200 L et vide les alertes des étapes précédentes : l'écran repart propre.
- **Ce que fait « Préparer la démo de crise » :** une réinitialisation complète, mais les humidités repartent de valeurs proches des seuils de survie : tomate 59 %, pomme de terre 47 %, basilic 40 % (58,6 / 46,7 / 39,5 % à l'écran 3,5 s plus tard). L'arrosage normal est suspendu jusqu'au lancement de la crise, 45 s au maximum : passé ce délai il reprend seul et le préréglage est perdu (recliquer sur « Préparer »).
- **Le jury voit** (mesuré, identique dans 3 essais consécutifs) :
  - toute la page passe à l'orange, badge « MODE CRISE », compteur qui descend depuis 3:00, budget de 9,0 L, alerte critique « Crise activée… », et la pastille du réservoir devient rouge : « Recyclage coupé : eau contaminée » ;
  - la carte **Basilic devient rouge vers 50 à 54 s** de crise (humidité 24,5 %), sa pompe ne démarre jamais, et elle finit à 7,5 % ;
  - la **pompe de la pomme de terre** s'allume vers 82 à 86 s (à 36,7 %) et s'arrête 6 s plus tard (à 40,3 %) ; la **pompe de la tomate** s'allume vers 112 à 116 s (à 42 %) et s'arrête 6 s plus tard (à 46,2 %) ; la pomme de terre est arrosée une seconde fois vers 162 à 166 s. Jamais deux pompes en même temps ;
  - la barre de budget monte par paliers jusqu'à **4,8 L sur 9,0 L (53 %)**, avec l'alerte « Budget d'eau de crise consommé à 50 % » vers 2 min 45 ; le réservoir passe de 200 L à 195,2 L, sans aucun retour d'eau ;
  - tomate et pomme de terre ne descendent pas sous **39,8 %** et **34,85 %** (seuils de survie : 35 % et 30 %) ;
  - la lumière : 1 minute de jour, puis 0 lux jusqu'à la fin.
- **Je dis :** « Pour gagner du temps, on part d'une ferme qui a déjà souffert : on a réglé les humidités près des seuils de survie, sinon, en 3 minutes, la tomate et la pomme de terre n'auraient pas eu besoin d'eau. Le rationnement, lui, est réel : le recyclage est contaminé, on le coupe, et on n'a plus que 40 % de la consommation normale, et non 40 % du réservoir, car 40 % de 200 L feraient 80 L, plus que ce que la ferme consomme normalement. Sur 3 minutes, la consommation normale est de 22,5 L, donc un budget de 9,0 L. Le basilic est sacrifié ; tomate et pomme de terre sont arrosées seulement quand elles approchent de leur seuil de survie, une pompe à la fois ; et on réduit la lumière pour ralentir l'évaporation. »
- **Si on demande si c'est truqué :** les règles sont exactement celles de la crise complète de 8 minutes (16,1 L sur 24,0 L, 67 %, mesuré) : seul le point de départ change, pour qu'en 3 minutes le rationnement se voie. Les humidités de départ et la suspension de l'arrosage normal pendant 45 s au maximum sont décrites dans le code et dans TOPICS.md.

### 5. Fin de crise et bilan (environ 30 s)

- **Je clique :** rien, j'attends 0:00. Pour aller plus vite : « Arrêter la crise » (le bilan indique alors « manuelle »).
- **Le jury voit :** la page repasse au vert et la pastille redevient verte : « Recyclage actif ». Une alerte INFO « Fin de crise (automatique) : 4.8 L consommés sur 9.0 L (53 % du budget)… Toutes les zones vitales sont restées au-dessus du seuil de survie » (valeurs de nos essais). Le panneau crise affiche « Dernier bilan : 4,8 L consommés sur 9,0 L (53 %) ».
- **Je dis :** « Retour automatique au mode normal. Le budget n'a jamais été dépassé et la tomate et la pomme de terre n'ont jamais franchi leur seuil de survie. Sur la crise complète de 8 minutes, soit 48 h simulées : 67 % du budget utilisé, minima à 39,8 % et 34,8 %. »

## Étape optionnelle : les vrais capteurs (si l'ESP32 est branché)

À montrer plutôt pendant l'étape 1 (fonctionnement normal), pendant que la ferme tourne seule. Deux capteurs, à montrer l'un après l'autre.

**Humidité du sol :**
- **Je fais :** je sors la fourche du capteur de l'eau (ou du terreau humide).
- **Le jury voit :** sur la carte Tomate, le badge passe de « Simulé » (gris) à « Capteur réel » (vert), avec la valeur brute du capteur affichée à côté ; l'humidité chute en quelques secondes, suit exactement la valeur du capteur, et si elle passe sous le seuil d'arrosage (60 %), la pompe démarre.
- **Je replonge** la fourche dans l'eau : l'humidité remonte, suit la valeur réelle, et la pompe s'arrête une fois le seuil dépassé.

**Température de l'air :**
- **Je fais :** je pose un doigt sur le capteur quelques secondes.
- **Le jury voit :** un petit point vert apparaît à côté de « Température », sur la carte Tomate ; le chiffre monte de quelques dixièmes de degré (mesuré : 25,8 puis 26,5 °C).
- **Je dis :** « Ici, ce n'est plus une simulation : ce sont de vrais capteurs, branchés par câble sur un ESP32. L'API remplace les mesures simulées de la tomate par ces valeurs réelles. L'humidité pilote l'arrosage comme avant, avec de vraies données ; la température, elle, est seulement affichée, elle ne déclenche encore aucune décision. Les deux capteurs sont indépendants : si je débranche l'un, l'autre continue, et chacun repasse tout seul en simulé au bout de 15 secondes sans nouvelle mesure. »
- **Si on demande pourquoi une seule zone :** le Wi-Fi de l'ESP32 ne fonctionne pas sur ce PC (alimentation du port USB-C), donc les mesures passent par câble série ; on n'a câblé qu'une seule zone pour la démonstration, mais l'API et le dashboard sont prêts à en accueillir d'autres de la même façon.

## Modifier le programme de l'ESP32

Le port série (`COM3`) ne peut être ouvert que par **un seul programme à la fois**. Tant que `pont_capteur.py` tourne, l'IDE Arduino ne peut pas téléverser (erreur de type « accès refusé » ou « port occupé »). Pour changer le programme de l'ESP32 pendant la préparation, sans toucher au reste de la ferme (simulateur, API, dashboard restent allumés) :

```powershell
.\pont-stop.ps1     # libère COM3
#  ... téléverser depuis l'IDE Arduino, puis le fermer (lui aussi retient le port) ...
.\pont-start.ps1    # relance le pont, dans sa propre fenêtre
```

- `pont-stop.ps1` arrête la fenêtre du pont (et, par sécurité, tout `pont_capteur.py` resté actif ailleurs, même une fenêtre perdue de vue), puis **vérifie réellement** que le port est libre en l'ouvrant brièvement — le même test que ferait l'IDE Arduino — et vous le confirme avant de téléverser.
- `pont-start.ps1` relance uniquement le pont ; il vérifie d'abord que le broker MQTT répond. À utiliser une fois le téléversement terminé et l'IDE Arduino fermé.
- Sur le dashboard, pendant que le pont est arrêté, la carte Tomate repasse en badge « Simulé » (humidité) et perd son repère vert (température) au bout de 15 secondes (comportement normal, voir « Étape optionnelle » ci-dessus) : rien à faire, elle rebascule sur le réel dès la première mesure reçue après `pont-start.ps1`.
- Ces deux scripts ne démarrent ni n'arrêtent jamais le simulateur, l'API, le dashboard ni le broker Docker : `.\start.ps1` / `.\stop.ps1` restent les commandes pour tout arrêter ou tout relancer.

## Questions probables

- **Pourquoi 40 % de la consommation normale et pas du réservoir ?** Le réservoir est plein (200 L) : 40 % de son contenu ne serait pas une contrainte. La contrainte réelle est ce que la ferme consomme (60 L pour 8 min), donc 24 L.
- **Et si le budget est épuisé ?** Avant chaque tour de pompe, l'API vérifie qu'il reste assez d'eau, sinon elle refuse la pompe et crée une alerte critique. Le budget n'est jamais dépassé (vérifié par trois mesures indépendantes).
- **48 h en 8 minutes ?** Facteur 360 (172 800 s ÷ 480 s). La durée se règle avec `-DureeCrise`, et le budget est recalculé pour la durée choisie.
- **Tout est simulé ?** Oui : capteurs, pompes, évaporation, fuite, recyclage. Les échanges passent bien par un vrai broker MQTT, comme sur du matériel.
- **Le circuit fermé est-il simulé ?** Oui, de façon simple : à chaque tour, 90 % de l'eau pompée revient dans le réservoir, toujours, sans traitement ni délai. L'eau d'une fuite est perdue, et en crise le recyclage est coupé.
- **Pourquoi MQTT ?** Léger, standard de l'IoT, et il sépare proprement capteurs, décisions et affichage.

## En cas de problème

- **« API injoignable » ou page figée :** regarder la fenêtre « SpaceFarm - API », puis arrêter et relancer avec les deux commandes `powershell -ExecutionPolicy Bypass -File ...` ci-dessus (environ 30 s). Si la ferme est simplement dans un mauvais état (fuite oubliée, crise en cours, réservoir bas), le bouton « Réinitialiser la ferme » suffit.
- **Le rationnement ne se voit pas en crise (barre de budget à 0) :** la crise a été lancée trop tard après « Préparer » (plus de 45 s) : cliquer de nouveau sur « Préparer la démo de crise », puis sur « Activer la crise ».
- **Un PC du jury ne se connecte pas :** pare-feu, voir le README. Sinon, projeter depuis le PC qui héberge tout.
- **Écran de portable (1366x768) :** la page défile un peu vers le bas, mais rien ne se chevauche.
- **Plan B :** captures dans `dashboard/captures/` (mode normal, fuite, mode crise avec pompe de survie en marche) et résultats de `tests\test_crise.py` dans le README.
