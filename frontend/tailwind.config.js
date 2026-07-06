/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(38 18% 84%)",
        background: "hsl(42 28% 95%)",
        foreground: "hsl(220 36% 12%)",
        muted: "hsl(42 28% 91%)",
        primary: "hsl(183 64% 28%)",
        accent: "hsl(34 76% 52%)",
        success: "hsl(151 39% 36%)",
        danger: "hsl(358 64% 48%)"
      },
      boxShadow: {
        panel: "0 10px 30px rgba(28, 34, 43, 0.07), 0 1px 0 rgba(255, 255, 255, 0.7) inset"
      }
    }
  },
  plugins: []
};

