/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary:  { DEFAULT: '#1D4ED8', light: '#3B82F6', dark: '#1E3A8A' },
        surface:  { DEFAULT: '#F8FAFC', card: '#FFFFFF', border: '#E2E8F0' },
        text:     { primary: '#0F172A', secondary: '#475569', muted: '#94A3B8' },
        success:  '#16A34A',
        warning:  '#D97706',
        danger:   '#DC2626',
        low:      '#FEF3C7',   // low attendance highlight
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: { DEFAULT: '0.5rem', lg: '0.75rem', xl: '1rem' },
    }
  },
  plugins: []
}
