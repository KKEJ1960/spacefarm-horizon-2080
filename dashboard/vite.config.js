import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // strictPort : si le port 5173 est déjà pris, Vite s'arrête au lieu de changer de port
  // (sinon l'équipe ne saurait plus quelle adresse ouvrir).
  server: { port: 5173, strictPort: true },
})
