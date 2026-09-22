import { nombre } from '../formater.js'
import Num from './Num.jsx'

// Barre horizontale à fond plat (pas de dégradé), avec des repères facultatifs (traits fins + légende).
// pourcent : remplissage de 0 à 100 ; couleur : couleur d'état (vert, ambre, rouge) ou d'accent.
// reperes : [{ position (0-100), couleur, nom, valeur }], par exemple le seuil de survie d'une zone.
export default function Barre({ pourcent, couleur, reperes = [], className = '' }) {
  const rempli = Math.max(0, Math.min(100, pourcent ?? 0))

  return (
    <>
      <div className={`barre ${className}`}>
        <div className="barre-remplissage" style={{ width: `${rempli}%`, background: couleur }} />
        {reperes.map((r) => (
          <div key={r.nom + r.valeur} className="repere" style={{ left: `${r.position}%`, background: r.couleur }} />
        ))}
      </div>

      {reperes.length > 0 && (
        <div className="legende-barre">
          {reperes.map((r) => (
            <span key={r.nom + r.valeur} style={{ left: `${r.position}%`, color: r.couleur }}>
              {r.nom} <Num>{nombre(r.valeur, 0)}</Num> %
            </span>
          ))}
        </div>
      )}
    </>
  )
}
