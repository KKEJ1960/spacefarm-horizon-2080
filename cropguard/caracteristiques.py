# Analyse d'une feuille : on isole la FEUILLE (on ecarte le fond : terre, paillage,
# ombres), puis on repere les parties qui s'ecartent du vert sain a l'INTERIEUR de la
# feuille : taches noires, taches blanches, jaunissement, pourriture.
#
# Honnete : c'est une heuristique couleur + forme, pas un modele entraine par maladie.
# Elle marche le mieux sur un gros plan d'une feuille. Le verdict global (sain / a
# surveiller / malade) vient du modele entraine (extraire + entrainer.py), qui recoit
# maintenant AUSSI la part de chaque symptome : il "voit" donc les taches.

from PIL import Image, ImageFilter
import numpy as np

TAILLE = 160

COULEURS = {
    "Jaunissement":   (245, 180, 40),
    "Taches blanches":(90, 170, 255),
    "Taches noires":  (255, 120, 40),
    "Pourriture":     (245, 60, 100),
}

def _bool_to_img(m):
    return Image.fromarray((m * 255).astype("uint8"))

def _dilate(m, it):
    img = _bool_to_img(m)
    for _ in range(it):
        img = img.filter(ImageFilter.MaxFilter(5))
    return np.asarray(img) > 127

def _erode(m, it):
    img = _bool_to_img(m)
    for _ in range(it):
        img = img.filter(ImageFilter.MinFilter(5))
    return np.asarray(img) > 127

def _ouvrir(m):
    return _dilate(_erode(m, 1), 1)   # enleve les pixels isoles

def _analyse(chemin):
    petite = Image.open(chemin).convert("RGB").resize((TAILLE, TAILLE))
    rgb = np.asarray(petite)
    hsv = np.asarray(petite.convert("HSV"), dtype=np.float32)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    # 1) Tissu sain : vert a vert clair (lime), assez sature, pas sombre.
    #    (teintes en 0-255 : ~48 = jaune-vert, ~120 = vert-bleu ; sous 48 = jaune)
    sain = (h >= 48) & (h <= 120) & (s > 55) & (v > 55)

    # 2) Feuille = tissu sain avec ses trous rebouches (fermeture morphologique).
    #    Les taches interieures rejoignent la feuille ; le fond exterieur reste dehors.
    feuille = _erode(_dilate(sain, 6), 6)
    # On analyse un peu a l'INTERIEUR du bord : l'anneau feuille/fond n'est ni vraiment
    # sain ni vraiment fond, il ne doit pas etre compte comme un symptome.
    interieur = _erode(feuille, 2)
    aire = max(int(interieur.sum()), 1)

    # 3) Symptomes = pixels de l'interieur de la feuille qui ne sont PAS du tissu sain.
    anormal = interieur & (~sain)
    reste = anormal.copy()

    noir = reste & (v < 70)
    reste = reste & (~noir)
    blanc = reste & (v > 195) & (s < 55)
    reste = reste & (~blanc)
    jaune = reste & (h < 48) & (s > 70) & (v >= 100)
    reste = reste & (~jaune)
    pourri = reste & (h < 45) & (s >= 25) & (v >= 45) & (v <= 160)

    masques = {
        "Taches noires":  _ouvrir(noir),
        "Taches blanches":_ouvrir(blanc),
        "Jaunissement":   _ouvrir(jaune),
        "Pourriture":     _ouvrir(pourri),
    }
    parts = {nom: round(float(m.sum()) / aire * 100, 1) for nom, m in masques.items()}
    return rgb, hsv, sain, interieur, masques, parts

# --- Ce que recoit le modele entraine ---
def extraire(chemin):
    rgb, hsv, sain, feuille, masques, parts = _analyse(chemin)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    aire = max(int(feuille.sum()), 1)

    # histogramme de teinte sur le tissu SAIN (12 tranches)
    hist, _ = np.histogram(h[sain], bins=12, range=(0, 255))
    hist = hist / max(int(sain.sum()), 1)

    # parts de symptomes (0..1) : le modele "voit" enfin les taches
    sympt = np.array([parts["Taches noires"], parts["Taches blanches"],
                      parts["Jaunissement"], parts["Pourriture"]], dtype=np.float32) / 100.0
    total = float(sum(m.sum() for m in masques.values())) / aire
    part_saine = float(sain.sum()) / aire

    extra = np.array([total, part_saine, s.mean() / 255, v.mean() / 255], dtype=np.float32)
    return np.concatenate([hist.astype(np.float32), sympt, extra])

# --- Ce qu'affiche le tableau de bord ---
def analyser_symptomes(chemin):
    *_, masques, parts = _analyse(chemin)
    total = round(min(sum(parts.values()), 100.0), 1)
    dominant = max(parts, key=parts.get)
    if parts[dominant] < 6:
        dominant = None
    return parts, dominant, total

def part_atteinte(chemin):
    *_, parts = _analyse(chemin)
    return round(min(sum(parts.values()), 100.0), 1)

def image_annotee(chemin):
    rgb, hsv, sain, feuille, masques, parts = _analyse(chemin)
    arr = rgb.copy()
    for nom, m in masques.items():
        couleur = np.array(COULEURS[nom])
        arr[m] = (0.4 * arr[m] + 0.6 * couleur).astype("uint8")
    return Image.fromarray(arr).resize(Image.open(chemin).size)
