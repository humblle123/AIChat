/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      boxShadow: {
        glow: '0 0 0 1px rgba(14, 165, 233, 0.08), 0 20px 50px rgba(2, 6, 23, 0.45)',
      },
    },
  },
  plugins: [],
};
