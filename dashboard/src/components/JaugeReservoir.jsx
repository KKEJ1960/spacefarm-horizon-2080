import { nombre } from '../formater.js'

// Jauge circulaire du réservoir, en litres et en pourcentage.
// Orange sous 30 %, rouge sous 10 % (mêmes seuils que les alertes de l'API).
export default function JaugeReservoir({ litres, capacite, consommationTotale, recyclageActif }) {
  const pourcent = litres === null ? 0 : (litres / capacite) * 100

  let couleur = 'var(--ok)'
  if (pourcent < 10) couleur = 'var(--danger)'
  else if (pourcent < 30) couleur = 'var(--attention)'

  return (
    <section className="carte">
      <h2>Réservoir d'eau</h2>
      <div className="jauge-zone">
        {/* Cercle rempli à "pourcent" % grâce à un dégradé conique */}
        <div
          className="jauge"
          style={{ background: `conic-gradient(${couleur} ${pourcent}%, var(--bord) 0)` }}
        >
          <div className="jauge-centre">
            <span className="jauge-pourcent">{litres === null ? '—' : nombre(pourcent, 0)} %</span>
          </div>
        </div>
        <div>
          <p className="jauge-litres">{nombre(litres)} L</p>
          <p className="texte-doux">sur {nombre(capacite, 0)} L</p>
          <p className="texte-doux">Consommé depuis le début&nbsp;: {nombre(consommationTotale)}&nbsp;L</p>
        </div>
      </div>

      {/* Recyclage de l'eau : vert quand il marche, rouge quand il est coupé (crise) */}
      {recyclageActif !== null && (
        <p className={recyclageActif ? 'recyclage recyclage-actif' : 'recyclage recyclage-coupe'}>
          {recyclageActif ? 'Recyclage actif' : 'Recyclage coupé : eau contaminée'}
        </p>
      )}
    </section>
  )
}
