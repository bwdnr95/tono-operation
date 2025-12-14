/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      keyframes: {
        "tono-rotate": {
          "0%": { transform: "rotate(0deg) scale(1)" },
          "50%": { transform: "rotate(6deg) scale(1.03)" },
          "100%": { transform: "rotate(0deg) scale(1)" },
        },
      },
      animation: {
        "tono-rotate": "tono-rotate 2.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
