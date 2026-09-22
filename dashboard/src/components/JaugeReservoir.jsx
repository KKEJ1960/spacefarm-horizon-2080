import { nombre } from '../formater.js'
import Num from './Num.jsx'
import Barre from './Barre.jsx'

// Niveau du réservoir, en litres et en pourcentage.
// Ambre sous 30 %, rouge sous 10 % (mêmes seuils que les alertes de l'API).
export default function JaugeReservoir({ litres, capacite, consommationTotale, recyclageActif }) {
  const pourcent = litres === null ? 0 : (litres / capacite) * 100

  let couleur = 'var(--ok)'
  if (pourcent < 10) couleur = 'var(--danger)'
  else if (pourcent < 30) couleur = 'var(--attention)'

  return (
    <section className="carte">
      <div className="carte-titre">
        <h2>Réservoir d'eau</h2>
        <span className="etiquette">
          <Num>{litres === null ? '—' : nombre(pourcent, 0)}</Num> %
        </span>
      </div>

      <p className="jauge-litres">
        <Num>{nombre(litres)}</Num>
        <span className="unite">L</span>
      </p>
      <p className="texte-doux reservoir-detail">
        sur <Num>{nombre(capacite, 0)}</Num> L · consommé depuis le début&nbsp;:{' '}
        <Num>{nombre(consommationTotale)}</Num>&nbsp;L
      </p>

      <Barre
        pourcent={pourcent}
        couleur={couleur}
        reperes={[
          { position: 10, couleur: 'var(--danger)', nom: '', valeur: 10 },
          { position: 30, couleur: 'var(--attention)', nom: '', valeur: 30 },
        ]}
      />

      {/* Recyclage de l'eau : vert quand il marche, ambre quand il est coupé (crise) */}
      {recyclageActif !== null && (
        <p className={recyclageActif ? 'recyclage recyclage-actif' : 'recyclage recyclage-coupe'}>
          <span className={recyclageActif ? 'point' : 'point point-attention'} />
          {recyclageActif ? 'Recyclage actif' : 'Recyclage coupé : eau contaminée'}
        </p>
      )}
    </section>
  )
}
