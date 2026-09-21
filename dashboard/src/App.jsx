import { useCallback, useEffect, useState } from 'react'
import {
  API_URL,
  INTERVALLE_MS,
  activerCrise,
  arreterCrise,
  lireAlertes,
  lireCrise,
  lireEtat,
  preparerDemoCrise,
  reinitialiserFerme,
  simulerFuite,
} from './api.js'
import CarteZone from './components/CarteZone.jsx'
import JaugeReservoir from './components/JaugeReservoir.jsx'
import ListeAlertes from './components/ListeAlertes.jsx'
import PanneauCrise from './components/PanneauCrise.jsx'
import PanneauSimulation from './components/PanneauSimulation.jsx'

export default function App() {
  // Dernières données reçues de l'API
  const [etat, setEtat] = useState(null)
  const [alertes, setAlertes] = useState([])
  const [crise, setCrise] = useState(null)
  const [recuLe, setRecuLe] = useState(Date.now())   // heure de la dernière réponse
  const [erreur, setErreur] = useState(false)        // vrai si l'API ne répond pas

  // Interroge les 3 routes de l'API en même temps
  const charger = useCallback(async () => {
    try {
      const [nouvelEtat, nouvellesAlertes, nouvelleCrise] = await Promise.all([lireEtat(), lireAlertes(), lireCrise()])
      setEtat(nouvelEtat)
      setAlertes(nouvellesAlertes)
      setCrise(nouvelleCrise)
      setRecuLe(Date.now())
      setErreur(false)
    } catch {
      setErreur(true)   // on garde les dernières valeurs affichées
    }
  }, [])

  // Au démarrage puis toutes les 2 secondes
  useEffect(() => {
    charger()
    const id = setInterval(charger, INTERVALLE_MS)
    return () => clearInterval(id)   // on arrête la boucle quand la page est fermée
  }, [charger])

  // Boutons : on envoie l'ordre à l'API, puis on recharge tout de suite l'affichage
  async function basculerCrise() {
    try {
      if (crise?.actif) await arreterCrise()
      else await activerCrise()
    } catch {
      setErreur(true)
    }
    charger()
  }

  async function basculerFuite() {
    try {
      await simulerFuite(fuite ? 'OFF' : 'ON')
    } catch {
      setErreur(true)
    }
    charger()
  }

  // Remet la ferme à zéro (préparation de la démo) puis recharge l'affichage
  async function reinitialiser() {
    try {
      await reinitialiserFerme()
    } catch {
      setErreur(true)
    }
    charger()
  }

  // Prépare la démo de crise : réinitialisation avec des humidités proches des seuils de survie
  async function preparerDemo() {
    try {
      await preparerDemoCrise()
    } catch {
      setErreur(true)
    }
    charger()
  }

  const enCrise = crise?.actif === true
  // L'état de la fuite vient de l'API (pas de la page) : il reste juste après un rechargement
  const fuite = etat?.fuite_simulee === true
  // Zones classées par priorité (1 = la plus importante)
  const zones = etat ? Object.entries(etat.zones).sort((a, b) => a[1].priorite - b[1].priorite) : []

  return (
    // data-mode change toutes les couleurs d'accent (voir styles.css)
    <div className="page" data-mode={enCrise ? 'crise' : 'normal'}>
      <header className="entete">
        <div>
          <h1>SpaceFarm · Horizon 2080</h1>
          <p className="texte-doux">Ferme hydroponique autonome · simulation</p>
        </div>
        <div className="entete-etat">
          {erreur && <span className="badge badge-erreur">API injoignable ({API_URL})</span>}
          <span className={enCrise ? 'badge badge-mode badge-mode-crise' : 'badge badge-mode'}>
            {enCrise ? 'MODE CRISE' : 'Mode normal'}
          </span>
        </div>
      </header>

      <main>
        <div className="zones">
          {zones.map(([id, zone]) => (
            <CarteZone key={id} zone={zone} />
          ))}
        </div>

        {/* Rangée du bas : 4 panneaux côte à côte sur grand écran (tout tient sans défiler en 1920x1080) */}
        <div className="bas">
          <JaugeReservoir
            litres={etat?.reservoir_litres ?? null}
            capacite={etat?.reservoir_capacite_litres ?? 200}
            consommationTotale={etat?.consommation_totale_litres ?? 0}
            recyclageActif={etat ? etat.recyclage_actif : null}
          />
          <PanneauSimulation
            fuite={fuite}
            onBasculer={basculerFuite}
            onReinitialiser={reinitialiser}
            onPreparerDemo={preparerDemo}
            demoPrete={etat?.demo_crise_prete === true}
            demoSecondes={etat?.demo_crise_secondes_restantes ?? 0}
          />
          <PanneauCrise crise={crise} recuLe={recuLe} onBasculer={basculerCrise} />
          <ListeAlertes alertes={alertes} />
        </div>
      </main>
    </div>
  )
}
