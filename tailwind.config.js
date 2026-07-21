/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // FIX: templates use `xs:` classes (e.g. xs:flex-row on the newsletter form)
      // but no `xs` breakpoint was defined, so those classes were never generated
      // and silently ignored — the newsletter form stacked vertically on all
      // mobile widths instead of switching to a row layout above 480px.
      screens: {
        xs: '480px',
      },
      colors: {
        // RETHEME v2: dark green GRADIENT background (dark mode) with a
        // bright neon-lime accent, matching the reference mobile-app
        // mockup. Light mode keeps the pale-green look from the previous
        // pass — this reference is an inherently dark-themed design, and
        // the site already defaults to dark mode, so this becomes the
        // primary experience most visitors see.
        luxe: {
          light: '#F0F7F1',        // pale green page background (light mode only)
          dark: '#070D08',         // gradient END — near-black deep green (dark mode)
          darkStart: '#173C22',    // gradient START — rich forest green (dark mode)
          gray: '#16241B',         // dark green-gray (dropdowns, mobile menu dark bg)
          black: '#0F1B13',        // deepest green-black
          charcoal: '#1B2A20',     // dark green-gray secondary surface
          gold: '#8CE93B',         // PRIMARY ACCENT — bright neon lime (was forest green #1F5D3A)
          goldMuted: '#A6F24D',    // brighter lime for hover states (hover brightens on dark bg)
          white: '#F5FAF6',        // soft pale green-white
          surface: '#FFFFFF',      // card background, light mode
          surfaceDark: '#10231A',  // card background, dark mode
          muted: '#6B8577',        // muted sage-gray for secondary text
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