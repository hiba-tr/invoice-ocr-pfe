/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Couleurs de fond
        lightBg: '#f5f3ff', // Violet très clair
        darkBg: '#0f172a',  // Bleu nuit
        // Couleurs d'accentuation
        primaryLight: '#8b5cf6', // Violet
        primaryDark: '#3b82f6',  // Bleu
      }
    },
  },
  plugins: [],
}