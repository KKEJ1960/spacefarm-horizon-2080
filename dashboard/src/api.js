// ---------------------------------------------------------------------------
// Adresse de l'API FastAPI (spacefarm/api.py)
// ---------------------------------------------------------------------------
// window.location.hostname = l'adresse par laquelle on a ouvert le dashboard :
//   - ouvert sur ce PC avec http://127.0.0.1:5173        -> API sur http://127.0.0.1:8000
//   - ouvert par un collègue avec http://192.168.x.x:5173 -> API sur http://192.168.x.x:8000
// (un "127.0.0.1" écrit en dur ne marcherait que sur le PC qui héberge l'API)
export const API_URL = `http://${window.location.hostname}:8000`

// Le dashboard interroge l'API toutes les 2 secondes
export const INTERVALLE_MS = 2000

// Appelle l'API et renvoie la réponse JSON (lève une erreur si l'API ne répond pas correctement)
async function appeler(chemin, methode = 'GET') {
  const reponse = await fetch(API_URL + chemin, { method: methode })
  if (!reponse.ok) {
    throw new Error(`${chemin} : erreur ${reponse.status}`)
  }
  return reponse.json()
}

// Lectures
export const lireEtat = () => appeler('/etat')
export const lireAlertes = () => appeler('/alertes')
export const lireCrise = () => appeler('/crise')

// Actions
export const activerCrise = () => appeler('/crise/activer', 'POST')
export const arreterCrise = () => appeler('/crise/desactiver', 'POST')
export const simulerFuite = (etat) => appeler(`/simulation/fuite?etat=${etat}`, 'POST') // etat = 'ON' ou 'OFF'
export const reinitialiserFerme = () => appeler('/reinitialiser', 'POST')
export const preparerDemoCrise = () => appeler('/preparer-demo-crise', 'POST')
