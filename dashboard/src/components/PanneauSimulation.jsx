// Panneau de simulation : fuite d'eau, remise à zéro de la ferme, préparation de la démo de crise.
// L'API détecte la fuite toute seule et crée une alerte critique.
export default function PanneauSimulation({ fuite, onBasculer, onReinitialiser, onPreparerDemo, demoPrete, demoSecondes }) {
  return (
    <section className="carte">
      <h2>Simulation</h2>
      <button className={fuite ? 'bouton bouton-fuite-actif' : 'bouton bouton-fuite'} onClick={onBasculer}>
        {fuite ? 'Arrêter la fuite (OFF)' : 'Simuler une fuite (ON)'}
      </button>
      <p className="texte-doux">
        {fuite ? 'Fuite en cours : le réservoir perd 1 L de plus par tour.' : 'Aucune fuite simulée.'}
      </p>

      {/* Deux boutons côte à côte pour préparer la démo */}
      <div className="boutons-ligne">
        {/* Remise à zéro normale : réservoir plein, humidités de départ, alertes vidées, plus de fuite ni de crise */}
        <button className="bouton bouton-reinit" onClick={onReinitialiser}>
          Réinitialiser la ferme
        </button>
        {/* Remise à zéro, mais avec des humidités proches des seuils de survie : une ferme qui a "déjà souffert" */}
        <button className="bouton bouton-reinit bouton-demo" onClick={onPreparerDemo}>
          Préparer la démo de crise
        </button>
      </div>

      {demoPrete && (
        <p className="demo-prete">
          Démo prête : lancez la crise dans les {demoSecondes} s (l'arrosage normal est en pause).
        </p>
      )}
    </section>
  )
}
