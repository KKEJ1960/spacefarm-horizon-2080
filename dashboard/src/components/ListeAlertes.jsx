import { heure } from '../formater.js'

const NOMS_NIVEAUX = { info: 'Information', attention: 'Attention', critique: 'Critique' }
const MAX_AFFICHEES = 30

// Liste des alertes : la plus récente en haut, couleur selon le niveau (gris, ambre, rouge).
export default function ListeAlertes({ alertes }) {
  // L'API renvoie les alertes de la plus ancienne à la plus récente : on inverse
  const recentes = [...alertes].reverse().slice(0, MAX_AFFICHEES)

  return (
    <section className="carte carte-alertes">
      <h2>Alertes</h2>
      {recentes.length === 0 && <p className="texte-doux">Aucune alerte.</p>}
      <ul className="liste-alertes">
        {recentes.map((alerte, i) => (
          <li key={alerte.date + i} className={`alerte alerte-${alerte.niveau}`}>
            <div className="alerte-entete">
              <span className="alerte-niveau">{NOMS_NIVEAUX[alerte.niveau] ?? alerte.niveau}</span>
              <span>{alerte.zone}</span>
              <span className="alerte-heure num">{heure(alerte.date)}</span>
            </div>
            <div>{alerte.message}</div>
          </li>
        ))}
      </ul>
    </section>
  )
}
