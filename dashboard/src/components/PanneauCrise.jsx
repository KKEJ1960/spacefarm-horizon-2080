import { useEffect, useState } from 'react'
import { minutesSecondes, nombre } from '../formater.js'

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
  const tempsRestant = actif ? crise.temps_restant_secondes - (maintenant - recuLe) / 1000 : 0
  const total = crise.budget_total_litres
  const pourcentConsomme = total > 0 ? Math.min(100, (crise.budget_consomme_litres / total) * 100) : 0
  const bilan = crise.bilan

  return (
    <section className="carte carte-crise">
      <h2>Crise : contamination du recyclage</h2>

      <button className={actif ? 'bouton bouton-crise-actif' : 'bouton bouton-crise'} onClick={onBasculer}>
        {actif ? 'Arrêter la crise' : 'Activer la crise'}
      </button>

      {actif ? (
        <>
          <p className="compteur">{minutesSecondes(tempsRestant)}</p>
          <p className="texte-doux">temps restant avant le retour au mode normal</p>
        </>
      ) : (
        <p className="texte-doux">
          Aucune crise en cours. En crise, le budget d'eau est limité à 40&nbsp;% de la consommation normale.
        </p>
      )}

      {/* Barre du budget d'eau : partie consommée / partie restante */}
      {total > 0 && (
        <>
          <div className="barre barre-budget">
            <div className="barre-remplissage" style={{ width: `${pourcentConsomme}%`, background: 'var(--accent)' }} />
          </div>
          <div className="budget-legende">
            <span>Consommé : <strong>{nombre(crise.budget_consomme_litres)} L</strong></span>
            <span>Restant : <strong>{nombre(crise.budget_restant_litres)} L</strong></span>
            <span>Budget : <strong>{nombre(total)} L</strong></span>
          </div>
        </>
      )}

      {actif && crise.zones_en_danger.length > 0 && (
        <p className="alerte-danger">
          Zones en danger : {crise.zones_en_danger.map((z) => z.nom + (z.vitale ? '' : ' (sacrifiée)')).join(', ')}
        </p>
      )}

      {!actif && bilan && (
        <p className="texte-doux">
          Dernier bilan : {nombre(bilan.budget_consomme_litres)} L consommés sur {nombre(bilan.budget_total_litres)} L (
          {nombre(bilan.budget_utilise_pourcent, 0)} %).
        </p>
      )}
    </section>
  )
}
