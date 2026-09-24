# CropGuard : detection de maladies des feuilles par analyse de photo, service independant de
# l'API SpaceFarm (module ajoute par un membre de l'equipe, integre au reste du projet).
#
# Principe : parcourt en boucle le dossier flux/ (photos des zones), classe chaque feuille avec
# un modele entraine (RandomForest, voir entrainer.py et caracteristiques.py), publie une alerte
# MQTT quand c'est malade ou a surveiller, et sert son propre petit tableau de bord (port 8100).
# La sante calculee est aussi publiee sur cropguard/<zone>/sante ; l'API SpaceFarm (api.py) s'y
# abonne pour arroser un peu plus tot une zone dont les feuilles sont en souffrance.
#
# Ce service n'est PAS lance automatiquement par start.ps1 : le lancer a la main. Si scikit-learn
# est bloque hors conteneur (politique de securite Windows), voir Dockerfile (methode testee) :
#   docker build -t spacefarm-cropguard . ; docker run -d --name cropguard -p 8100:8100 spacefarm-cropguard
# Sinon, directement en Python (depuis ce dossier, ses propres dependances, voir requirements.txt) :
#   pip install -r requirements.txt
#   python -m uvicorn cropguard:app --host 0.0.0.0 --port 8100
# Puis ouvrir http://127.0.0.1:8100

import glob
import io
import json
import os
import threading
import time
from datetime import datetime, timezone

import joblib
import paho.mqtt.client as mqtt
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from caracteristiques import extraire, image_annotee, analyser_symptomes

BASE = os.path.dirname(os.path.abspath(__file__))
BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
INTERVALLE = float(os.getenv("INTERVALLE", "4"))
SEUIL_MALADE = float(os.getenv("SEUIL_MALADE", "0.60"))       # proba au-dela : malade
SEUIL_SURVEILLANCE = float(os.getenv("SEUIL_SURVEILLANCE", "0.35"))  # entre les deux : a surveiller
IRRIGATION_AUTO = os.getenv("IRRIGATION_AUTO", "0") == "1"

NOMS = {"zone1": "Tomate", "zone2": "Pomme de terre", "zone3": "Basilic"}
ZONES = ("zone1", "zone2", "zone3")

modele = joblib.load(os.path.join(BASE, "modele.joblib"))

courant = {"image": None, "verdict": None, "confiance": 0.0, "sante": 0.0,
           "atteinte": 0.0, "zone": "zone1", "nom": NOMS["zone1"],
           "symptomes": {}, "dominant": None, "date": None}
stats = {"total": 0, "saines": 0, "surveiller": 0, "malades": 0}
zones = {}
historique = []
alertes = []
verrou = threading.Lock()

client = mqtt.Client()
try:
    client.connect_async(BROKER, PORT)
    client.loop_start()
except Exception as e:
    print("Broker MQTT indisponible pour l'instant :", e)

def zone_de(nom):
    for z in ZONES:
        if nom.startswith(z):
            return z
    # pas de prefixe : on repartit les feuilles sur les trois zones, de facon stable
    return ZONES[sum(nom.encode()) % 3]

def niveau(proba):
    if proba >= SEUIL_MALADE:
        return "malade"
    if proba >= SEUIL_SURVEILLANCE:
        return "surveiller"
    return "saine"

def publier(topic, message):
    try:
        client.publish(topic, message)
    except Exception:
        pass

def boucle():
    i = 0
    dernier = {}
    while True:
        images = sorted(glob.glob(os.path.join(BASE, "flux", "*")))
        if not images:
            time.sleep(INTERVALLE)
            continue
        chemin = images[i % len(images)]
        i += 1
        nom = os.path.basename(chemin)
        try:
            proba = float(modele.predict_proba(extraire(chemin).reshape(1, -1))[0][1])
            symptomes, dominant, atteinte = analyser_symptomes(chemin)
        except Exception as e:
            print("analyse impossible :", nom, e)
            time.sleep(INTERVALLE)
            continue

        verdict = niveau(proba)
        sante = round((1 - proba) * 100, 1)
        confiance = round(max(proba, 1 - proba) * 100, 1)
        zone = zone_de(nom)
        date = datetime.now(timezone.utc).isoformat()

        with verrou:
            courant.update({"image": nom, "verdict": verdict, "confiance": confiance,
                            "sante": sante, "atteinte": atteinte, "zone": zone,
                            "nom": NOMS.get(zone, zone), "symptomes": symptomes,
                            "dominant": dominant, "date": date})
            stats["total"] += 1
            stats[{"saine": "saines", "surveiller": "surveiller", "malade": "malades"}[verdict]] += 1
            zones[zone] = {"nom": NOMS.get(zone, zone), "sante": sante,
                           "verdict": verdict, "atteinte": atteinte, "date": date}
            historique.append({"sante": sante, "verdict": verdict})
            del historique[:-24]

        publier(f"cropguard/{zone}/sante", json.dumps({"valeur": sante, "unite": "%", "date": date}))

        if verdict in ("malade", "surveiller") and dernier.get(nom) != verdict:
            niv = "critique" if verdict == "malade" else "attention"
            mot = "malade" if verdict == "malade" else "a surveiller"
            detail = f", symptome principal : {dominant}" if dominant else ""
            alerte = {"date": date, "niveau": niv, "zone": zone,
                      "message": f"Feuille {mot} ({NOMS.get(zone, zone)}), surface atteinte {atteinte:.0f}%{detail}"}
            with verrou:
                alertes.append(alerte)
                del alertes[:-50]
            publier("cropguard/alertes", json.dumps(alerte))
            if IRRIGATION_AUTO and verdict == "malade":
                publier(f"spacefarm/{zone}/cmd/pompe", "ON")

        dernier[nom] = verdict
        time.sleep(INTERVALLE)

threading.Thread(target=boucle, daemon=True).start()

app = FastAPI()

@app.get("/etat")
def get_etat():
    with verrou:
        taux = round(stats["saines"] / stats["total"] * 100, 1) if stats["total"] else 0.0
        return JSONResponse({
            "courant": dict(courant),
            "stats": dict(stats, taux=taux),
            "zones": dict(zones),
            "historique": list(historique),
        })

@app.get("/alertes")
def get_alertes():
    with verrou:
        return JSONResponse(list(reversed(alertes)))

@app.get("/image/courante")
def image_courante():
    with verrou:
        nom = courant["image"]
    if not nom:
        return JSONResponse({"erreur": "aucune image"}, status_code=404)
    return FileResponse(os.path.join(BASE, "flux", nom))

@app.get("/image/annotee")
def image_annotee_ep():
    with verrou:
        nom = courant["image"]
    if not nom:
        return JSONResponse({"erreur": "aucune image"}, status_code=404)
    img = image_annotee(os.path.join(BASE, "flux", nom))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")

@app.get("/", response_class=HTMLResponse)
def page():
    return PAGE

PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CropGuard</title>
<style>
  :root{ color-scheme:dark;
    --fond:#0e1116; --carte:#161b22; --bord:#22272e;
    --encre:#e6edf3; --encre2:#9aa5b1; --encre3:#6e7681;
    --vert:#3fb950; --rouge:#f85149; --ambre:#d29922; }
  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--fond); color:var(--encre);
        font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .haut{ padding:22px 28px; border-bottom:1px solid var(--bord);
         display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  .haut h1{ margin:0; font-size:22px; }
  .haut p{ margin:0; color:var(--encre2); font-size:14px; }
  .lien-sf{ margin-left:auto; color:var(--encre2); text-decoration:none; font-size:14px; border:1px solid var(--bord); padding:6px 12px; border-radius:8px; }
  .lien-sf:hover{ color:var(--encre); border-color:var(--encre3); }
  .live{ margin-left:16px; font-size:12px; color:var(--encre2); display:flex; align-items:center; gap:7px; }
  .live::before{ content:""; width:8px; height:8px; border-radius:50%; background:var(--vert);
                 box-shadow:0 0 0 0 rgba(63,185,80,.5); animation:p 2s infinite; }
  @keyframes p{ 0%{box-shadow:0 0 0 0 rgba(63,185,80,.5)} 70%{box-shadow:0 0 0 7px rgba(63,185,80,0)} 100%{box-shadow:0 0 0 0 rgba(63,185,80,0)} }
  .zone-contenu{ padding:20px 28px; max-width:none; margin:0; }
  .kpis{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:16px; margin-bottom:16px; }
  .tuile{ background:var(--carte); border:1px solid var(--bord); border-radius:12px; padding:18px 20px; }
  .tuile .n{ font-size:30px; font-weight:600; line-height:1.1; }
  .tuile .l{ color:var(--encre2); font-size:13px; margin-top:6px; display:flex; align-items:center; gap:7px; }
  .point{ width:9px; height:9px; border-radius:50%; }
  .p-vert{ background:var(--vert); } .p-ambre{ background:var(--ambre); } .p-rouge{ background:var(--rouge); }
  .barre-fine{ height:6px; border-radius:3px; background:#0e1116; margin-top:12px; overflow:hidden; }
  .barre-fine > i{ display:block; height:100%; border-radius:3px; }
  .grille{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; align-items:start; }
  .carte{ background:var(--carte); border:1px solid var(--bord); border-radius:12px; padding:20px; }
  .carte h2{ margin:0 0 16px; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--encre2); }
  .duo{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .duo figure{ margin:0; }
  .duo figcaption{ color:var(--encre3); font-size:11px; margin-top:5px; text-align:center; }
  .photo{ width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:10px; background:#0e1116; }
  .verdict{ display:flex; align-items:center; gap:11px; margin-top:16px; }
  .verdict .pt{ width:13px; height:13px; border-radius:50%; }
  .verdict .mot{ font-size:24px; font-weight:600; }
  .saine .pt{ background:var(--vert); } .saine .mot{ color:var(--vert); }
  .surveiller .pt{ background:var(--ambre); } .surveiller .mot{ color:var(--ambre); }
  .malade .pt{ background:var(--rouge); } .malade .mot{ color:var(--rouge); }
  .sous{ color:var(--encre2); font-size:13px; margin-top:8px; }
  .barre{ height:10px; border-radius:5px; background:#0e1116; margin-top:6px; overflow:hidden; }
  .barre > i{ display:block; height:100%; border-radius:5px; }
  .zligne{ margin-bottom:16px; }
  .zligne:last-child{ margin-bottom:0; }
  .zligne .t{ display:flex; justify-content:space-between; font-size:14px; margin-bottom:2px; }
  .zligne .t span:last-child{ color:var(--encre2); }
  .activite{ display:flex; align-items:flex-end; gap:4px; height:90px; }
  .activite > i{ flex:1; border-radius:3px 3px 0 0; min-height:4px; opacity:.9; }
  .sympt{ margin-top:12px; display:flex; flex-direction:column; gap:8px; }
  .sympt .l{ display:flex; align-items:center; gap:9px; font-size:14px; color:#9aa5b1; }
  .sympt .l b{ color:#e6edf3; font-weight:600; }
  .pastille-s{ width:11px; height:11px; border-radius:3px; }
  ul{ list-style:none; margin:0; padding:0; }
  li{ padding:11px 0; border-bottom:1px solid var(--bord); font-size:14px; }
  li:last-child{ border-bottom:none; }
  li .h{ color:var(--encre3); font-size:12px; margin-top:2px; }
  .vide{ color:var(--encre2); font-size:14px; }
</style>
</head>
<body>
  <div class="haut">
    <h1>CropGuard &middot; Horizon 2080</h1>
    <p>Detection de maladies des feuilles &middot; analyse d'image locale</p>
    <a id="lien-sf" class="lien-sf" href="#" target="_blank" rel="noopener">SpaceFarm &#8599;</a>
    <span class="live">en direct</span>
  </div>
  <div class="zone-contenu">
    <div class="kpis">
      <div class="tuile"><div class="n" id="k-total">0</div><div class="l">Analyses</div></div>
      <div class="tuile"><div class="n" id="k-saines">0</div><div class="l"><span class="point p-vert"></span>Saines</div></div>
      <div class="tuile"><div class="n" id="k-surv">0</div><div class="l"><span class="point p-ambre"></span>A surveiller</div></div>
      <div class="tuile"><div class="n" id="k-malades">0</div><div class="l"><span class="point p-rouge"></span>Malades</div></div>
      <div class="tuile"><div class="n" id="k-taux">0 %</div><div class="l">Taux de sante</div>
        <div class="barre-fine"><i id="k-taux-b" style="width:0%"></i></div></div>
    </div>
    <div class="grille">
      <div class="carte">
        <h2>Feuille analysee</h2>
        <div class="duo">
          <figure><img id="photo" class="photo" alt="feuille"><figcaption>Photo</figcaption></figure>
          <figure><img id="photo-a" class="photo" alt="zones atteintes"><figcaption>Zones atteintes</figcaption></figure>
        </div>
        <div id="verdict" class="verdict"><span class="pt"></span><span class="mot" id="mot">En attente</span></div>
        <div class="sous" id="culture"></div>
        <div class="sous">Surface atteinte <span id="atteinte">0</span> %</div>
        <div class="sous">Confiance <span id="confiance">0</span> %</div>
        <div class="barre"><i id="conf-b" style="width:0%"></i></div>
        <div class="sympt" id="symptomes"></div>
      </div>
      <div class="carte">
        <h2>Sante par zone</h2>
        <div id="zones"><div class="vide">En attente de donnees.</div></div>
        <h2 style="margin-top:22px">Activite recente</h2>
        <div class="activite" id="activite"></div>
      </div>
      <div class="carte">
        <h2>Dernieres alertes</h2>
        <ul id="alertes"><li class="vide">Aucune alerte.</li></ul>
      </div>
    </div>
  </div>
<script>
function couleur(s){ return s>=60 ? 'var(--vert)' : (s>=40 ? 'var(--ambre)' : 'var(--rouge)'); }
function couleurVerdict(v){ return v==='malade' ? 'var(--rouge)' : (v==='surveiller' ? 'var(--ambre)' : 'var(--vert)'); }
const COULEUR_SYMPT = {'Jaunissement':'#F5B428','Taches blanches':'#5AAAFF','Taches noires':'#FF7828','Pourriture':'#F53C64'};
function motVerdict(v){ return v==='malade' ? 'Malade' : (v==='surveiller' ? 'A surveiller' : 'Saine'); }
async function rafraichir(){
  try{
    const e = await (await fetch('/etat')).json();
    document.getElementById('k-total').textContent = e.stats.total;
    document.getElementById('k-saines').textContent = e.stats.saines;
    document.getElementById('k-surv').textContent = e.stats.surveiller;
    document.getElementById('k-malades').textContent = e.stats.malades;
    document.getElementById('k-taux').textContent = e.stats.taux + ' %';
    const tb = document.getElementById('k-taux-b');
    tb.style.width = e.stats.taux + '%'; tb.style.background = couleur(e.stats.taux);

    const c = e.courant, bloc = document.getElementById('verdict');
    if(c.verdict){
      bloc.className = 'verdict ' + c.verdict;
      document.getElementById('mot').textContent = motVerdict(c.verdict);
      document.getElementById('culture').textContent = 'Culture : ' + (c.nom || c.zone) + ' (' + c.zone + ')';
      document.getElementById('atteinte').textContent = c.atteinte;
      const sy = document.getElementById('symptomes');
      const items = Object.entries(c.symptomes || {}).filter(function(e){ return e[1] > 0; });
      sy.innerHTML = items.length ? items.map(function(e){
        return '<div class="l"><span class="pastille-s" style="background:'+(COULEUR_SYMPT[e[0]]||'#9aa5b1')+'"></span>'+e[0]+' <b>'+e[1]+' %</b></div>';
      }).join('') : '<div class="l" style="color:#6e7681">Aucun symptome marque</div>';
      document.getElementById('confiance').textContent = c.confiance;
      const cb = document.getElementById('conf-b');
      cb.style.width = c.confiance + '%'; cb.style.background = couleurVerdict(c.verdict);
      const t = Date.now();
      document.getElementById('photo').src = '/image/courante?t=' + t;
      document.getElementById('photo-a').src = '/image/annotee?t=' + t;
    }

    const z = e.zones, ordre = ['zone1','zone2','zone3'];
    const zc = document.getElementById('zones');
    const lignes = ordre.filter(k => z[k]).map(k => {
      const d = z[k];
      return '<div class="zligne"><div class="t"><span>'+d.nom+'</span><span>'+d.sante+' %</span></div>'+
             '<div class="barre"><i style="width:'+d.sante+'%;background:'+couleur(d.sante)+'"></i></div></div>';
    });
    zc.innerHTML = lignes.length ? lignes.join('') : '<div class="vide">En attente de donnees.</div>';

    document.getElementById('activite').innerHTML = e.historique.map(h =>
      '<i style="height:'+Math.max(h.sante,6)+'%;background:'+couleurVerdict(h.verdict)+'"></i>'
    ).join('');

    const a = await (await fetch('/alertes')).json();
    const ul = document.getElementById('alertes');
    ul.innerHTML = a.length ? a.map(x =>
      '<li><div>'+x.message+'</div><div class="h">'+new Date(x.date).toLocaleTimeString('fr-FR')+' &middot; '+x.zone+'</div></li>'
    ).join('') : '<li class="vide">Aucune alerte.</li>';
  }catch(err){}
}
document.getElementById('lien-sf').href = 'http://' + location.hostname + ':5173';   // port du dashboard SpaceFarm
rafraichir();
setInterval(rafraichir, 2000);
</script>
</body>
</html>"""
