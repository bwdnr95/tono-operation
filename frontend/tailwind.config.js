/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // 기존 className(bg-dark-*) 호환 유지 (하지만 라이트 SaaS 토큰으로 매핑)
        dark: {
          bg: "#F7F8F6",          // 페이지 배경 (가볍게)
          surface: "#FFFFFF",     // 헤더/패널
          card: "#FFFFFF",        // 카드
          panel: "#E6E7E3",       // 브랜드 primary(연한 회색) - 필요할 때만

          border: "rgba(26,26,26,0.12)",
          "border-strong": "rgba(26,26,26,0.20)",

          text: "#1A1A1A",
          muted: "#5F5F5F",

          accent: "#B6E63A",
          "accent-hover": "#C8F04D",
        },

        tono: {
          bg: "#F7F8F6",
          panel: "#E6E7E3",
          surface: "#FFFFFF",
          accent: "#B6E63A",
          text: "#1A1A1A",
          muted: "#5F5F5F",
          stroke: "rgba(26,26,26,0.12)",
          "stroke-strong": "rgba(26,26,26,0.20)",
        },
      },
      boxShadow: {
        soft: "0 12px 30px rgba(26, 26, 26, 0.10)",
        lift: "0 18px 40px rgba(26, 26, 26, 0.14)",
      },
      fontFamily: {
        sans: ["Pretendard", "Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        tono: "24px",
        "tono-lg": "32px",
      },
      maxWidth: {
        tono: "1320px",
      },
    },
  },
  plugins: [],
};
