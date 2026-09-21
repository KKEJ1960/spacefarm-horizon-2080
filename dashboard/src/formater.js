// Petites fonctions d'affichage, en format français (virgule décimale)

// nombre(58.24, 1) -> "58,2"   |   nombre(null) -> "—" (pas encore de mesure)
export function nombre(valeur, decimales = 1) {
  if (valeur === null || valeur === undefined) return '—'
  return valeur.toLocaleString('fr-FR', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })
}

// minutesSecondes(125) -> "2:05"
export function minutesSecondes(secondes) {
  const total = Math.max(0, Math.round(secondes))
  const minutes = Math.floor(total / 60)
  const reste = String(total % 60).padStart(2, '0')
  return `${minutes}:${reste}`
}

// heure("2080-01-01T12:34:56+00:00") -> "12:34:56" (heure locale)
export function heure(dateIso) {
  return new Date(dateIso).toLocaleTimeString('fr-FR')
}
