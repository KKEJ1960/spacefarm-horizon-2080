// Affiche une valeur numérique déjà formatée (par exemple "63,8") en police à chasse fixe.
// La virgule d'une police à chasse fixe occupe la largeur d'un chiffre et crée un trou :
// on la resserre un peu (classe "virgule") pour que "63,8" reste lisible.
export default function Num({ children, className = '' }) {
  const [entier, decimales] = String(children).split(',')
  return (
    <span className={`num ${className}`.trim()}>
      {decimales === undefined ? (
        entier
      ) : (
        <>
          {entier}
          <span className="virgule">,</span>
          {decimales}
        </>
      )}
    </span>
  )
}
