/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#edf5ff',
          100: '#d9eafd',
          200: '#b8d9fb',
          300: '#8dc1f8',
          400: '#5ca0f2',
          500: '#2b6cb0',
          600: '#255f9c',
          700: '#1f507f',
          800: '#1b4468',
          900: '#18395a',
        },
      },
      boxShadow: {
        card: '0 10px 28px rgba(33, 73, 112, 0.08)',
      },
      fontFamily: {
        sans: ['Manrope', 'Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
