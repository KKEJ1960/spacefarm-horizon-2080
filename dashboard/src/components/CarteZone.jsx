import { nombre } from '../formater.js'

// Une carte pour une zone de culture.
// La carte devient rouge quand l'humidité passe sous le seuil de survie.
export default function CarteZone({ zone }) {
  const humidite = zone.humidite
  const enDanger = humidite !== null && humidite < zone.seuil_survie

  // Couleur de la barre : rouge sous la survie, orange sous le seuil d'arrosage, vert sinon
  let couleur = 'var(--ok)'
  if (humidite !== null && humidite < zone.seuil_survie) couleur = 'var(--danger)'
  else if (humidite !== null && humidite < zone.seuil_arrosage) couleur = 'var(--attention)'

  return (
    <section className={enDanger ? 'carte carte-danger' : 'carte'}>
      <div className="carte-titre">
        <h2>{zone.nom}</h2>
        <span className={zone.vitale ? 'badge badge-vitale' : 'badge badge-non-vitale'}>
          {zone.vitale ? 'Vitale' : 'Non vitale'}
        </span>
      </div>

      {enDanger && <p className="alerte-danger">EN DANGER : humidité sous le seuil de survie</p>}

      {/* Humidité : gros chiffre + barre avec les deux seuils */}
      <p className="humidite">
        {nombre(humidite)} <span className="unite">% d'humidité</span>
      </p>
      <div className="barre">
        <div className="barre-remplissage" style={{ width: `${humidite ?? 0}%`, background: couleur }} />
        <div className="repere repere-survie" style={{ left: `${zone.seuil_survie}%` }} />
        <div className="repere repere-arrosage" style={{ left: `${zone.seuil_arrosage}%` }} />
      </div>
      <div className="legende-barre">
        <span className="legende-survie" style={{ left: `${zone.seuil_survie}%` }}>
          survie {zone.seuil_survie} %
        </span>
        <span className="legende-arrosage" style={{ left: `${zone.seuil_arrosage}%` }}>
          arrosage {zone.seuil_arrosage} %
        </span>
      </div>

      {/* Autres mesures */}
      <div className="mesures">
        <div>
          <span className="mesure-nom">Température</span>
          <span className="mesure-valeur">{nombre(zone.temperature)} °C</span>
        </div>
        <div>
          <span className="mesure-nom">pH</span>
          <span className="mesure-valeur">{nombre(zone.ph, 2)}</span>
        </div>
        <div>
          <span className="mesure-nom">Luminosité</span>
          <span className="mesure-valeur">{nombre(zone.luminosite, 0)} lux</span>
        </div>
        <div>
          <span className="mesure-nom">Eau consommée</span>
          <span className="mesure-valeur">{nombre(zone.consommation_litres)} L</span>
        </div>
      </div>

      <p className={zone.pompe === 'ON' ? 'pompe pompe-on' : 'pompe'}>
        Pompe {zone.pompe === 'ON' ? 'en marche' : zone.pompe === 'OFF' ? 'arrêtée' : '—'}
      </p>
    </section>
  )
}
