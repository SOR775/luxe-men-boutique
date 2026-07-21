/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        luxe: {
          light: '#F8FAFC',
          dark: '#050505',
          gray: '#1F2937',
          black: '#111827',
          charcoal: '#1F2937',
          gold: '#C8A24C',
          goldMuted: '#D6B86B',
          white: '#F8FAFC',
          surface: '#FFFFFF',
          surfaceDark: '#0F172A',
          muted: '#6B7280',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Poppins', 'sans-serif'],
      }
    }
  },
  plugins: [],
}