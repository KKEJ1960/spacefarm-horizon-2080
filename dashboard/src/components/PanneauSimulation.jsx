import Num from './Num.jsx'

// Barre secondaire "Outils de simulation" : fuite d'eau, remise à zéro de la ferme, préparation de la démo de crise.
// L'API détecte la fuite toute seule et crée une alerte critique.
export default function PanneauSimulation({ fuite, onBasculer, onReinitialiser, onPreparerDemo, demoPrete, demoSecondes }) {
  return (
    <section className="outils" aria-label="Outils de simulation">
      <h2 className="outils-titre">Outils de simulation</h2>

      <button className={fuite ? 'bouton bouton-actif' : 'bouton'} onClick={onBasculer}>
        {fuite ? 'Arrêter la fuite' : 'Simuler une fuite'}
      </button>
      {/* Remise à zéro normale : réservoir plein, humidités de départ, alertes vidées, plus de fuite ni de crise */}
      <button className="bouton" onClick={onReinitialiser}>
        Réinitialiser la ferme
      </button>
      {/* Remise à zéro, mais avec des humidités proches des seuils de survie : une ferme qui a "déjà souffert" */}
      <button className="bouton" onClick={onPreparerDemo}>
        Préparer la démo de crise
      </button>

      {/* Ligne d'état à droite : la fuite ou la démo prête */}
      {fuite && (
        <span className="outils-etat outils-etat-attention">
          Fuite en cours : le réservoir perd 1 L de plus par tour.
        </span>
      )}
      {demoPrete && (
        <span className="outils-etat outils-etat-attention">
          Démo prête : lancez la crise dans les <Num>{demoSecondes}</Num> s (l'arrosage normal est en pause).
        </span>
      )}
    </section>
  )
}
