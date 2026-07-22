/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      screens: {
        xs: '480px',
      },
      colors: {
        // ══════════════════════════════════════════════
        //  LUXE WEARS — Brand Identity Palette
        //  Primary: Emerald Green (#0B6B3A)
        //  Secondary: White (#FFFFFF)
        //  Accent: Deep Red (#C62828)
        //  Accent Highlight: Soft Pink (#F8BBD0)
        //  Text: Charcoal (#222222)
        //  Border: #E5E7EB
        // ══════════════════════════════════════════════
        emerald: {
          brand:    '#0B6B3A',   // Primary — buttons, active states, CTAs
          hover:    '#08542D',   // Darker emerald for hover
          light:    '#E8F5E9',   // Pale emerald tint — section backgrounds
          50:       '#F0FDF4',
          100:      '#DCFCE7',
          200:      '#BBF7D0',
          500:      '#22C55E',
          600:      '#16A34A',
          700:      '#15803D',
          800:      '#166534',
          900:      '#14532D',
        },
        luxe: {
          // Surface & background
          cream:       '#FAFAF8',   // Warm white — light mode page bg
          surface:     '#FFFFFF',   // Card background light
          surfaceAlt:  '#F7F7F5',   // Slightly off-white, alt background
          dark:        '#0E1A14',   // Deep dark green-black (dark mode bg)
          darkStart:   '#0B1A12',   // Dark mode gradient start
          darkCard:    '#132219',   // Dark mode card surface
          darkBorder:  '#1E3328',   // Dark mode borders

          // Brand accents
          emerald:     '#0B6B3A',   // Replaces gold — primary brand
          emeraldHover:'#08542D',   // Hover state
          emeraldLight:'#E8F5E9',   // Soft tint for badges/highlights
          emeraldGlow: 'rgba(11,107,58,0.18)',

          // Accent colors
          red:         '#C62828',   // Destructive / sale badge
          redHover:    '#B71C1C',   // Red hover
          redLight:    '#FFEBEE',   // Soft red tint
          pink:        '#F8BBD0',   // Soft pink — highlight accent
          pinkHover:   '#F48FB1',   // Deeper pink for hover

          // Typography
          charcoal:    '#222222',   // Primary text (light mode)
          muted:       '#6B7280',   // Secondary/muted text
          faint:       '#9CA3AF',   // Faint text, placeholder

          // Borders
          border:      '#E5E7EB',   // Default border
          borderDark:  '#374151',   // Darker border
        },
        // Legacy support keys (used by existing templates)
        'luxe-gold':      '#0B6B3A',   // Remapped to emerald brand
        'luxe-goldMuted': '#08542D',   // Remapped to emerald hover
        'luxe-black':     '#222222',   // Charcoal text
        'luxe-white':     '#FAFAF8',   // Warm white
        'luxe-light':     '#F7F7F5',   // Light surface
        'luxe-dark':      '#0E1A14',   // Dark bg
        'luxe-darkStart': '#0B1A12',   // Dark gradient start
        'luxe-gray':      '#132219',   // Dark card
        'luxe-surface':   '#FFFFFF',
        'luxe-surfaceDark': '#132219',
        'luxe-muted':     '#6B7280',
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ['Poppins', 'sans-serif'],
        serif:   ['Cormorant Garamond', 'Georgia', 'serif'],
      },
      borderRadius: {
        'card':  '14px',
        'card-lg': '18px',
        'card-xl': '24px',
      },
      boxShadow: {
        'soft':      '0 4px 20px rgba(0,0,0,0.06)',
        'card':      '0 8px 30px rgba(0,0,0,0.08)',
        'card-hover':'0 16px 50px rgba(0,0,0,0.12)',
        'emerald':   '0 8px 30px rgba(11,107,58,0.25)',
        'emerald-lg':'0 16px 50px rgba(11,107,58,0.30)',
        'red':       '0 8px 25px rgba(198,40,40,0.30)',
      },
      animation: {
        'fade-up':       'fadeUp 0.6s ease-out forwards',
        'fade-in':       'fadeIn 0.4s ease-out forwards',
        'slide-in-right':'slideInRight 0.3s ease-out forwards',
        'slide-in-left': 'slideInLeft 0.3s ease-out forwards',
        'skeleton':      'skeleton 1.5s ease-in-out infinite',
        'bounce-soft':   'bounceSoft 2s ease-in-out infinite',
        'pulse-green':   'pulseGreen 2s ease-in-out infinite',
        'spin-slow':     'spin 3s linear infinite',
        'counter':       'counter 2s ease-out forwards',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(30px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-30px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        skeleton: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        bounceSoft: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        pulseGreen: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(11,107,58,0.4)' },
          '50%': { boxShadow: '0 0 0 8px rgba(11,107,58,0)' },
        },
        counter: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      transitionDuration: {
        '250': '250ms',
        '400': '400ms',
      },
    }
  },
  plugins: [],
}