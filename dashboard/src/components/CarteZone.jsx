import { nombre } from '../formater.js'
import Num from './Num.jsx'
import Barre from './Barre.jsx'

// Une carte pour une zone de culture.
// La carte passe en état "danger" quand l'humidité descend sous le seuil de survie.
// Les deux seuils (survie et arrosage) viennent de l'API : ils changent avec zones.json.
export default function CarteZone({ zone }) {
  const humidite = zone.humidite
  const enDanger = humidite !== null && humidite < zone.seuil_survie
  const souSeuilArrosage = humidite !== null && humidite < zone.seuil_arrosage

  // Couleurs d'état : rouge sous la survie, ambre sous le seuil d'arrosage, vert sinon
  const couleur = enDanger ? 'var(--danger)' : souSeuilArrosage ? 'var(--attention)' : 'var(--ok)'

  // Ligne d'état de la zone (toujours présente : la carte ne change pas de taille)
  let statut = (
    <span className="statut">
      <span className="point" />
      Humidité normale
    </span>
  )
  if (enDanger) {
    statut = <span className="statut statut-danger">En danger : sous le seuil de survie</span>
  } else if (souSeuilArrosage) {
    statut = (
      <span className="statut statut-attention">
        <span className="point point-attention" />
        Sous le seuil d'arrosage
      </span>
    )
  }

  return (
    <section className={enDanger ? 'carte carte-danger' : 'carte'}>
      <div className="carte-titre">
        <h2>{zone.nom}</h2>
        <span className="etiquette">
          {zone.vitale ? 'Vitale' : 'Non vitale'} · priorité <Num>{zone.priorite}</Num>
        </span>
      </div>

      {/* Humidité en grand, avec l'état de la zone à droite */}
      <div className="zone-etat">
        <div>
          <span className="mesure-nom">Humidité</span>
          <p className="humidite">
            <Num>{nombre(humidite)}</Num>
            <span className="unite">%</span>
          </p>
        </div>
        {statut}
      </div>

      {/* Barre d'humidité avec les repères de survie (rouge) et d'arrosage (ambre) */}
      <Barre
        pourcent={humidite}
        couleur={couleur}
        reperes={[
          { position: zone.seuil_survie, couleur: 'var(--danger)', nom: 'survie', valeur: zone.seuil_survie },
          { position: zone.seuil_arrosage, couleur: 'var(--attention)', nom: 'arrosage', valeur: zone.seuil_arrosage },
        ]}
      />

      {/* Autres mesures */}
      <div className="mesures">
        <div>
          <span className="mesure-nom">Température</span>
          <span className="mesure-valeur">
            <Num>{nombre(zone.temperature)}</Num>
            <span className="unite">°C</span>
          </span>
        </div>
        <div>
          <span className="mesure-nom">pH</span>
          <span className="mesure-valeur">
            <Num>{nombre(zone.ph, 2)}</Num>
          </span>
        </div>
        <div>
          <span className="mesure-nom">Luminosité</span>
          <span className="mesure-valeur">
            <Num>{nombre(zone.luminosite, 0)}</Num>
            <span className="unite">lux</span>
          </span>
        </div>
        <div>
          <span className="mesure-nom">Eau consommée</span>
          <span className="mesure-valeur">
            <Num>{nombre(zone.consommation_litres)}</Num>
            <span className="unite">L</span>
          </span>
        </div>
      </div>

      {/* Pompe : disque vert plein = en marche, disque vide = arrêtée */}
      <p className={zone.pompe === 'ON' ? 'pompe pompe-on' : 'pompe pompe-off'}>
        <span className={zone.pompe === 'ON' ? 'point' : 'point point-eteint'} />
        Pompe {zone.pompe === 'ON' ? 'en marche' : zone.pompe === 'OFF' ? 'arrêtée' : '—'}
      </p>
    </section>
  )
}
