import { useEffect, useState } from 'react'
import { minutesSecondes, nombre } from '../formater.js'
import Barre from './Barre.jsx'
import Num from './Num.jsx'

// Panneau du scénario de crise : bouton, compte à rebours, budget d'eau.
// "recuLe" = heure de la dernière réponse de l'API : sert à faire défiler le compte
// à rebours chaque seconde entre deux réponses (l'API n'est interrogée que toutes les 2 s).
export default function PanneauCrise({ crise, recuLe, onBasculer }) {
  const [maintenant, setMaintenant] = useState(Date.now())

  useEffect(() => {
    const id = setInterval(() => setMaintenant(Date.now()), 500)
    return () => clearInterval(id)
  }, [])

  if (!crise) {
    return (
      <section className="carte">
        <h2>Crise</h2>
        <p className="texte-doux">En attente de l'API…</p>
      </section>
    )
  }

  const actif = crise.actif
  const bilan = crise.bilan
  const tempsRestant = actif ? crise.temps_restant_secondes - (maintenant - recuLe) / 1000 : 0

  // La barre de budget est toujours visible. Pendant la crise : le budget en cours.
  // Sinon : le dernier bilan s'il existe, ou une barre vide (le budget est fixé à l'activation).
  const source = actif
    ? { total: crise.budget_total_litres, consomme: crise.budget_consomme_litres, restant: crise.budget_restant_litres }
    : bilan
      ? {
          total: bilan.budget_total_litres,
          consomme: bilan.budget_consomme_litres,
          restant: Math.max(0, bilan.budget_total_litres - bilan.budget_consomme_litres),
        }
      : null
  const pourcentConsomme = source && source.total > 0 ? (source.consomme / source.total) * 100 : 0

  // Couleur d'état du budget : vert dans les clous, ambre à partir de 80 %, rouge si dépassé
  let couleurBudget = 'var(--ok)'
  if (pourcentConsomme >= 100) couleurBudget = 'var(--danger)'
  else if (pourcentConsomme >= 80) couleurBudget = 'var(--attention)'

  const titreBudget = actif ? "Budget d'eau de la crise" : bilan ? "Budget d'eau du dernier bilan" : "Budget d'eau"

  return (
    <section className="carte carte-crise">
      <h2>Crise : contamination du recyclage</h2>

      <button className="bouton bouton-principal" onClick={onBasculer}>
        {actif ? 'Arrêter la crise' : 'Activer la crise'}
      </button>

      {/* Compte à rebours (ou état "aucune crise") : la hauteur de ce bloc ne change pas */}
      <div className="crise-etat">
        {actif ? (
          <>
            <p className="compteur num">{minutesSecondes(tempsRestant)}</p>
            <p className="texte-doux">temps restant avant le retour au mode normal</p>
          </>
        ) : (
          <>
            <p>Aucune crise en cours.</p>
            <p className="texte-doux">
              En crise, le budget d'eau est limité à 40&nbsp;% de la consommation normale.
            </p>
          </>
        )}
      </div>

      {/* Barre du budget d'eau : toujours affichée */}
      <div className="budget-titre">
        <span>{titreBudget}</span>
        {source && (
          <span>
            <Num>{nombre(pourcentConsomme, 0)}</Num> % utilisé
          </span>
        )}
      </div>
      <Barre pourcent={pourcentConsomme} couleur={couleurBudget} className="barre-budget" />
      {source ? (
        <div className="budget-legende">
          <span>Consommé <Num>{nombre(source.consomme)}</Num> L</span>
          <span>Restant <Num>{nombre(source.restant)}</Num> L</span>
          <span>Budget <Num>{nombre(source.total)}</Num> L</span>
        </div>
      ) : (
        <p className="budget-legende texte-doux">Le budget en litres est fixé à l'activation de la crise.</p>
      )}

      {actif && crise.zones_en_danger.length > 0 && (
        <p className="crise-note crise-danger">
          Zones en danger : {crise.zones_en_danger.map((z) => z.nom + (z.vitale ? '' : ' (sacrifiée)')).join(', ')}
        </p>
      )}
    </section>
  )
}
