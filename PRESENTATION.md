# SpaceFarm : une ferme qui se garde toute seule

*Projet Horizon 2080 : nourrir un équipage dans l'espace*

## 1. Le problème

Imaginez un vaisseau spatial très loin de la Terre. Impossible de le ravitailler en route. L'équipage doit donc produire sa propre nourriture, avec très peu d'eau, sans jamais pouvoir compter sur un magasin.

## 2. La solution

Nous avons imaginé une ferme sans terre, où les plantes poussent dans l'eau et se surveillent toutes seules : elle arrose au bon moment, gère la lumière, repère les fuites et prévient l'équipage. Quand l'eau devient rare, elle sait quelles plantes sauver en priorité. Pour l'instant, c'est surtout une simulation sur ordinateur : deux vrais capteurs (l'humidité du sol et la température de l'air, sur la tomate) sont aujourd'hui branchés par câble, le reste (pompes, plantes, autres capteurs) est encore simulé.

## 3. Comment ça marche

La ferme a quatre parties, chacune avec un rôle simple.

- **Les capteurs sont ses yeux et ses doigts.** Un capteur mesure quelque chose, comme un thermomètre. Toutes les 2 secondes, on mesure pour chaque culture l'humidité, la température, l'acidité de l'eau (le pH) et la lumière, et pour le réservoir son niveau. La plupart de ces capteurs sont virtuels : un programme calcule les chiffres. Deux vrais capteurs sont cependant branchés sur la tomate, reliés par câble à un petit ordinateur (un ESP32) — un pour l'humidité du sol, un pour la température de l'air — et leurs mesures remplacent celles du programme pour cette culture.
- **Le facteur, c'est la messagerie** (son nom technique : MQTT). Chaque mesure est une lettre que le facteur remet à ceux qui l'attendent. Il porte aussi les ordres, dans l'autre sens.
- **Le cerveau décide.** Ce programme (l'API) compare les mesures à des limites et envoie des ordres aux pompes et à la lumière.
- **Le tableau de bord, c'est celui d'une voiture :** un écran qui montre tout, avec quelques boutons.

Suivons une information, **de la plante jusqu'à l'écran** :
1. Le capteur mesure la tomate : 59,6 % d'humidité (limite d'arrosage : 60 %).
2. Le facteur porte ce chiffre au cerveau, en une fraction de seconde.
3. Le cerveau le garde ; l'écran le lui redemande toutes les 2 secondes et l'affiche.

Puis **de la décision jusqu'à la pompe** :
4. Le chiffre est sous la limite : le cerveau écrit « allume la pompe de la tomate », et le facteur porte l'ordre à la pompe.
5. La pompe démarre : le réservoir baisse, l'humidité remonte d'environ 2 points toutes les 2 secondes.
6. À 75 %, le cerveau ordonne d'arrêter la pompe.

## 4. Une journée normale

L'équipage n'a rien à faire.

- **Arrosage automatique.** La tomate est arrosée sous 60 % d'humidité, la pomme de terre sous 55 %, le basilic sous 50 %. La pompe s'arrête 15 points plus haut.
- **Jour et nuit accélérés.** La lumière reste allumée 2 minutes, puis s'éteint 1 minute. La nuit, les plantes s'assèchent deux fois moins vite.
- **Eau suivie de près.** La ferme compte l'eau bue par chaque culture et surveille un réservoir de 200 litres. Le circuit est fermé : 90 % de l'eau pompée y revient, si bien que le réservoir baisse à peine. Sous 30 %, elle prévient et passe en économie : plus d'eau pour le basilic, et la tomate puis la pomme de terre passent chacune leur tour. Sous 10 %, l'alerte devient rouge.

## 5. Quand quelque chose tourne mal : la fuite

Un bouton permet de « percer » le réservoir : il perd alors 1 litre de plus toutes les 2 secondes. Le cerveau n'en est pas informé. Il fait un simple calcul : « Le niveau a baissé de tant ; les pompes en marche n'expliquent que tant. » Si l'écart dépasse un demi-litre, une alerte rouge « fuite suspectée » est créée en environ une seconde dans nos essais (limite fixée : 30 secondes) et s'affiche à l'écran au plus 2 secondes plus tard. Quand la fuite s'arrête, un message bleu annonce le retour à la normale. L'eau perdue par la fuite n'est pas recyclée. Le cerveau prévient, mais il ne répare pas et ne localise pas la fuite.

## 6. La crise

Scénario : l'eau recyclée est contaminée, on coupe donc le recyclage. Pendant 48 heures (huit minutes dans la simulation, le temps est accéléré), la ferme doit tenir avec 40 % de l'eau habituelle.

**Comment on compte.** L'eau « habituelle » est celle qui compense l'évaporation des trois cultures pendant ces 48 heures : 60 litres. Le budget est donc 40 % de 60, soit **24 litres**. Nous n'avons pas pris 40 % du réservoir (80 litres) : c'est plus que la consommation normale, ce ne serait pas une crise. La ferme s'impose donc elle-même ce budget.

**Le choix difficile.** La tomate et la pomme de terre nourrissent l'équipage : elles sont « vitales ». Le basilic est un plaisir, pas une nécessité. Dès le début de la crise, on le sacrifie : plus une goutte pour lui.

**Les économies.**
- Les cultures vitales ne sont arrosées que quand elles approchent de leur limite de survie : la tomate sous 40 % (limite 35 %), la pomme de terre sous 35 % (limite 30 %). La pompe s'arrête à 45 % et 40 %.
- Une seule pompe à la fois, la tomate d'abord.
- Moins de lumière (1 minute de jour, 2 de nuit) : moins d'évaporation.
- Avant chaque tour de pompe, le cerveau vérifie qu'il reste de l'eau dans le budget ; sinon il refuse et prévient.
- Au bout des 48 heures, retour automatique au fonctionnement normal, avec un bilan.

**Le résultat, mesuré** (test automatique, crise complète de huit minutes) :
- **16,1 litres consommés sur 24,0 : 67 % du budget**, jamais dépassé. Trois mesures indépendantes donnent le même chiffre.
- La tomate n'est jamais descendue sous **39,8 %** (limite : 35 %), la pomme de terre sous **34,8 %** (limite : 30 %).
- Le basilic, sans une goutte, est tombé à 0 % d'humidité : perdu, comme prévu.
- Le recyclage reste coupé pendant toute la crise, puis retour automatique au fonctionnement normal après 481 secondes.

## 7. Ce que voit l'utilisateur à l'écran

Fond sombre et gros caractères, lisibles même projetés. L'écran se met à jour seul toutes les 2 secondes.

- **En haut :** le titre, une bande verte et une pastille verte « Mode normal ». Si le cerveau ne répond plus, une pastille rouge le signale.
- **Trois cartes, une par culture :** nom, étiquette « Vitale » (contour vert) ou « Non vitale » (gris), gros chiffre d'humidité et barre : verte quand tout va bien, jaune orangé sous la limite d'arrosage, rouge sous la limite de survie (deux traits marquent ces limites). Dessous : température, acidité, lumière, eau consommée, et la pompe, « arrêtée » ou « en marche » (bande bleue). Sous la limite de survie, toute la carte devient rouge : « EN DANGER ».
- **Le réservoir :** un anneau avec le pourcentage et les litres restants ; vert, jaune orangé sous 30 %, rouge sous 10 %. Dessous, une pastille verte « Recyclage actif », ou rouge « Recyclage coupé : eau contaminée » pendant la crise.
- **« Simuler une fuite » (contour bleu) :** le bouton devient bleu plein et propose « Arrêter la fuite ». « Réinitialiser la ferme » remet tout à zéro avant une démonstration, « Préparer la démo de crise » la remet dans un état déjà éprouvé.
- **Le panneau de crise :** « Activer la crise » (contour orange), puis « Arrêter la crise » (orange plein), avec un compte à rebours géant, la barre du budget d'eau et les zones en danger. Toute la page passe à l'orange : fond brun, bande orange, étiquette « MODE CRISE ». Un « dernier bilan » reste affiché ensuite.
- **Les alertes,** la plus récente en haut : bande bleue (information), jaune orangé (attention), rouge (critique).

## 8. Pourquoi c'est utile

Dans l'espace : moins de ravitaillement, une ferme qui réagit seule, une eau gérée au litre près. Sur Terre : les mêmes idées servent face aux sécheresses, dans les fermes urbaines et les serres (arroser juste assez, repérer vite une fuite). Notre projet ne remplace pas une vraie installation : il montre que ces règles fonctionnent.

## 9. Les limites, honnêtement

- **Presque tout est simulé.** Deux vrais capteurs (humidité du sol et température de l'air, sur la tomate, reliés par câble à un ESP32) ; le pH, la luminosité, les pompes et les plantes ne le sont pas. La température réelle est affichée mais ne déclenche encore aucune décision. Les limites d'arrosage et de survie ont été choisies par l'équipe, pas validées par des agronomes, et la simulation ne fait pas pousser les plantes.
- **La démonstration part d'une ferme préréglée.** Pour tenir en 3 minutes, elle démarre d'une ferme « qui a déjà souffert » ; les résultats chiffrés viennent de la crise complète de 8 minutes.
- **Le recyclage est très simple.** 90 % de l'eau pompée revient toujours, sans traitement ni délai ; la contamination est un bouton qui coupe ce retour et impose un budget.
- **Le logiciel n'utilise pas tout.** Température et acidité sont affichées mais ne déclenchent aucune décision ; la lumière suit un horaire fixe.
- **Testé sur un seul ordinateur, sans mot de passe** : un système d'atelier, pas un produit sécurisé.

**Prochaines étapes possibles :** d'autres vrais capteurs et de vraies pompes (deux capteurs réels existent déjà pour la tomate ; le cerveau et l'écran ont à peine changé pour les accueillir) ; des limites ajustées par des agronomes ; la croissance des plantes simulée ; la température et l'acidité utilisées pour décider ; un accès protégé. Un membre de l'équipe a aussi ajouté CropGuard, une détection de maladies des feuilles par photo (voir [cropguard/](cropguard/)) : le code fonctionne (lancé à part, dans un conteneur), mais il ne fait pas partie du déroulé principal de la démonstration.

## 10. Le pitch de 30 secondes

« Dans un vaisseau spatial, on ne peut pas faire ses courses. Notre ferme se garde toute seule : elle arrose au bon moment, gère la lumière, compte l'eau et repère une fuite en quelques secondes. Et si l'eau se contamine, elle choisit : elle sacrifie le basilic pour sauver la tomate et la pomme de terre. Dans nos essais, 48 heures de crise simulées ont été tenues avec 67 % du budget d'eau prévu. Deux vrais capteurs y sont déjà branchés, et la prochaine étape, ce sont de vraies pompes. »
