# Entraine le modele a distinguer les feuilles saines des feuilles malades,
# puis l'enregistre dans modele.joblib. A lancer une seule fois.
#   .venv/bin/python entrainer.py

import glob
import os
import sys

import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

from caracteristiques import extraire

BASE = os.path.dirname(os.path.abspath(__file__))

def charger(dossier, etiquette):
    X, y = [], []
    for chemin in sorted(glob.glob(os.path.join(BASE, "dataset", dossier, "*"))):
        try:
            X.append(extraire(chemin))
            y.append(etiquette)
        except Exception as e:
            print("image ignoree :", chemin, e)
    return X, y

X, y = [], []
for dossier, etiquette in [("sain", 0), ("malade", 1)]:
    Xi, yi = charger(dossier, etiquette)
    print(f"{dossier} : {len(yi)} images")
    X += Xi
    y += yi

X = np.array(X)
y = np.array(y)
if len(set(y)) < 2:
    sys.exit("Il faut des images dans dataset/sain ET dans dataset/malade.")

modele = RandomForestClassifier(n_estimators=300, random_state=42)

# Estimation honnete de la precision sur un petit jeu : validation croisee.
mini = int(np.bincount(y).min())
n = min(mini, 5)
if n >= 2:
    cv = StratifiedKFold(n_splits=n, shuffle=True, random_state=42)
    scores = cross_val_score(modele, X, y, cv=cv)
    print(f"Precision estimee : {scores.mean() * 100:.0f}% (validation croisee sur {n} decoupes)")
else:
    print("Trop peu d'images pour estimer la precision.")

modele.fit(X, y)
joblib.dump(modele, os.path.join(BASE, "modele.joblib"))
print("Modele enregistre dans modele.joblib")
