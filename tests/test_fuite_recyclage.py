r"""
Test de la détection de fuite AVEC le recyclage de l'eau.

Pourquoi ce test : avec le recyclage, 90 % de l'eau pompée revient dans le réservoir. Si l'API
comparait la baisse du réservoir au débit TOTAL des pompes, une fuite de 1 L passerait inaperçue
pendant qu'une pompe tourne (écart de 0,46 L, sous la tolérance de 0,5 L). L'API doit donc calculer
la baisse attendue en tenant compte du recyclage.

Ce test n'utilise ni le broker ni le simulateur : il appelle directement les fonctions de l'API avec
un faux client MQTT. Il dure quelques secondes.

Depuis la RACINE du projet, en PowerShell :
    spacefarm\.venv\Scripts\python.exe tests\test_fuite_recyclage.py

Code de sortie : 0 si tous les scénarios sont conformes, 1 sinon.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# On importe api.py (dans le dossier spacefarm)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "spacefarm"))
import api  # noqa: E402


class FauxClient:
    """Remplace le client MQTT : on ne publie rien."""

    def publish(self, topic, payload, retain=False):
        pass


api.client = FauxClient()
TOLERANCE = api.TOLERANCE_FUITE


def scenario(nom, recyclage, pompes_on, baisse, alerte_attendue):
    """
    recyclage : True/False (état du recyclage vu par l'API)
    pompes_on : liste des zones dont la pompe tourne
    baisse    : baisse observée du réservoir sur un tour (en litres)
    """
    api.statuts.clear()
    api.alertes.clear()
    api.suivi["ignorer_fuite_jusqua"] = 0.0
    api.etat["recyclage_actif"] = recyclage
    for zone_id in api.etat["zones"]:
        api.etat["zones"][zone_id]["pompe"] = "ON" if zone_id in pompes_on else "OFF"

    debit = sum(api.CONFIG["zones"][z]["debit_pompe"] for z in pompes_on)
    attendu = debit * ((1 - api.TAUX_RECYCLAGE) if recyclage else 1)
    ancien_niveau = 150.0
    api.evaluer_reservoir(ancien_niveau, ancien_niveau - baisse)

    alerte = any(a["niveau"] == "critique" and "Fuite" in a["message"] for a in api.alertes)
    ok = (alerte == alerte_attendue)
    sans_correction = (baisse - debit) > TOLERANCE   # ce que donnait l'ancien calcul
    print(f"{'OK   ' if ok else 'ECHEC'} | {nom:<40} | baisse {baisse:5.2f} L | attendu {attendu:4.2f} L | "
          f"alerte {'OUI' if alerte else 'non'} | (sans correction : {'OUI' if sans_correction else 'non'})")
    return ok


resultats = []
print("Recyclage actif (90 %) :")
resultats.append(scenario("pompe laitue en marche, pas de fuite", True, ["zone1"], 0.06, False))
resultats.append(scenario("pompe laitue en marche + fuite de 1 L", True, ["zone1"], 1.06, True))
resultats.append(scenario("3 pompes en marche + fuite de 1 L", True, ["zone1", "zone2", "zone3"], 1.14, True))
resultats.append(scenario("aucune pompe + fuite de 1 L", True, [], 1.0, True))
resultats.append(scenario("aucune pompe, pas de fuite", True, [], 0.0, False))

print("Recyclage coupé (crise) :")
resultats.append(scenario("pompe laitue en marche, pas de fuite", False, ["zone1"], 0.6, False))
resultats.append(scenario("pompe laitue en marche + fuite de 1 L", False, ["zone1"], 1.6, True))

# Fin de crise : l'API attend recyclage ON, mais le simulateur peut être au milieu d'un tour encore en OFF.
# L'API ne juge donc pas les fuites pendant deux tours après un changement de recyclage.
print("Changement de recyclage en plein tour :")
api.statuts.clear()
api.alertes.clear()
api.etat["recyclage_actif"] = False
api.suivi["ignorer_fuite_jusqua"] = 0.0
for zone_id in api.etat["zones"]:
    api.etat["zones"][zone_id]["pompe"] = "ON" if zone_id == "zone1" else "OFF"
api.changer_recyclage(True)             # ouvre la fenêtre "on ne juge pas les fuites"
api.evaluer_reservoir(150.0, 149.4)     # baisse de 0,6 L : le simulateur n'avait pas encore reçu le ON
pas_de_fausse_alerte = not any("Fuite" in a["message"] for a in api.alertes)
print(f"{'OK   ' if pas_de_fausse_alerte else 'ECHEC'} | pas de fausse alerte pendant la fenêtre de {2 * api.INTERVALLE:.0f} s")
resultats.append(pas_de_fausse_alerte)

api.suivi["ignorer_fuite_jusqua"] = 0.0     # la fenêtre est passée : la même mesure est jugée normalement
api.evaluer_reservoir(150.0, 149.4)
jugee_apres = any("Fuite" in a["message"] for a in api.alertes)
print(f"{'OK   ' if jugee_apres else 'ECHEC'} | après la fenêtre, la même mesure est jugée (la fenêtre n'est pas permanente)")
resultats.append(jugee_apres)

print(f"\nRésultat : {sum(resultats)}/{len(resultats)} scénarios conformes")
sys.exit(0 if all(resultats) else 1)
