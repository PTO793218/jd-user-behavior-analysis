/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(214 32% 91%)",
        background: "hsl(210 20% 98%)",
        foreground: "hsl(222 47% 11%)",
        muted: "hsl(210 40% 96%)",
        primary: "hsl(199 89% 34%)",
        accent: "hsl(39 92% 50%)",
        success: "hsl(158 64% 36%)",
        danger: "hsl(0 72% 51%)"
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15, 23, 42, 0.06)"
      }
    }
  },
  plugins: []
};

