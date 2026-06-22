/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        warm: {
          50: '#FDFBF7',
          100: '#F5F0E8',
          200: '#EEE8DB',
          300: '#E4DCCC',
          400: '#D8D0C0',
          500: '#C47A5A',
          600: '#B5694E',
          700: '#A05A42',
        },
      },
      boxShadow: {
        glow: '0 2px 12px rgba(28,26,23,0.06)',
      },
    },
  },
  plugins: [],
};
