/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"SF Pro Display"', '"SF Pro Text"', 'system-ui', '-apple-system',
          'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif',
        ],
      },
      colors: {
        // Apple Action Blue — the single interactive color
        apple: {
          blue: "#0066CC",
          "blue-focus": "#0071E3",
          "blue-on-dark": "#2997FF",
          green: "#30D158",
          red: "#FF453A",
          yellow: "#FFD60A",
          orange: "#FF9F0A",
          gray: "#8E8E93",
          "gray-5": "#E5E5EA",
          "gray-6": "#F5F5F7",
        },
        // Apple surface tokens (dark-mode adapted)
        surface: {
          DEFAULT: "#272729",
          secondary: "#2A2A2C",
          tertiary: "#252527",
          black: "#000000",
          card: "rgba(255,255,255,0.04)",
          "card-hover": "rgba(255,255,255,0.07)",
          border: "rgba(255,255,255,0.08)",
          "border-hover": "rgba(255,255,255,0.12)",
        },
        // Text on dark surfaces
        text: {
          primary: "#FFFFFF",
          secondary: "#CCCCCC",
          tertiary: "#7A7A7A",
          muted: "#333333",
        },
        // Light-surface tokens (for cards/parchment contrast)
        light: {
          canvas: "#FFFFFF",
          parchment: "#F5F5F7",
          pearl: "#FAFAFC",
          ink: "#1D1D1F",
          "ink-muted": "#7A7A7A",
          border: "#E0E0E0",
        },
      },
      spacing: {
        18: "4.5rem",
        22: "5.5rem",
        30: "7.5rem",
      },
      borderRadius: {
        xs: "5px",
        sm: "8px",
        md: "11px",
        lg: "18px",
        pill: "9999px",
      },
      animation: {
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.25s ease-out",
        "slide-down": "slideDown 0.25s ease-out",
        "scale-in": "scaleIn 0.15s ease-out",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        slideDown: { "0%": { opacity: "0", transform: "translateY(-6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        scaleIn: { "0%": { opacity: "0", transform: "scale(0.96)" }, "100%": { opacity: "1", transform: "scale(1)" } },
      },
    },
  },
  plugins: [],
};
