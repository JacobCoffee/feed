/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{html,js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#4584b6",
        secondary: "#ffde57",
        tertiary: "#606060",
      },
    },
  },
  plugins: [
    require("daisyui"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/aspect-ratio"),
  ],
  daisyui: {
    themes: [
      {
        mytheme: {
          primary: "#4584b6",
          secondary: "#ffde57",
          tertiary: "#606060",
        },
      },
    ],
  },
};
