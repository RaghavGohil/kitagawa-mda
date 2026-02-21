import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },

      /* ==================================================
         CORE UI — STRICT GRAYSCALE (NO DECORATIVE COLOR)
         ================================================== */
      colors: {
        border: "hsl(0 0% 20%)",
        input: "hsl(0 0% 18%)",
        ring: "hsl(0 0% 40%)",

        background: "hsl(0 0% 6%)",
        foreground: "hsl(0 0% 92%)",

        primary: {
          DEFAULT: "hsl(0 0% 85%)",
          foreground: "hsl(0 0% 8%)",
        },
        secondary: {
          DEFAULT: "hsl(0 0% 25%)",
          foreground: "hsl(0 0% 92%)",
        },
        muted: {
          DEFAULT: "hsl(0 0% 18%)",
          foreground: "hsl(0 0% 65%)",
        },
        accent: {
          DEFAULT: "hsl(0 0% 30%)",
          foreground: "hsl(0 0% 95%)",
        },
        destructive: {
          DEFAULT: "hsl(0 0% 28%)",
          foreground: "hsl(0 0% 95%)",
        },

        popover: {
          DEFAULT: "hsl(0 0% 10%)",
          foreground: "hsl(0 0% 90%)",
        },
        card: {
          DEFAULT: "hsl(0 0% 9%)",
          foreground: "hsl(0 0% 90%)",
        },

        /* ==================================================
           SIDEBAR / LEFT DRAWER — STILL GRAYSCALE
           ================================================== */
        sidebar: {
          DEFAULT: "hsl(0 0% 8%)",
          foreground: "hsl(0 0% 88%)",
          primary: "hsl(0 0% 80%)",
          "primary-foreground": "hsl(0 0% 10%)",
          accent: "hsl(0 0% 22%)",
          "accent-foreground": "hsl(0 0% 90%)",
          border: "hsl(0 0% 18%)",
          ring: "hsl(0 0% 40%)",
        },

        /* ==================================================
           SEMANTIC COLORS — ONLY WHERE MEANING EXISTS
           ================================================== */

        /* Status = operational meaning */
        status: {
          normal: "hsl(0 0% 60%)",        // neutral
          info: "hsl(210 12% 65%)",       // desaturated steel
          warning: "hsl(38 28% 55%)",     // muted amber
          critical: "hsl(0 35% 45%)",     // muted red
        },

        /* Anomaly = attention driver */
        anomaly: {
          low: "hsl(40 22% 60%)",
          medium: "hsl(30 32% 50%)",
          high: "hsl(0 38% 45%)",
        },

        /* Vessels stay neutral (no rainbow maps) */
        vessel: {
          cargo: "hsl(0 0% 65%)",
          tanker: "hsl(0 0% 55%)",
          fishing: "hsl(0 0% 45%)",
          passenger: "hsl(0 0% 70%)",
          military: "hsl(0 0% 35%)",
          unknown: "hsl(0 0% 50%)",
        },

        /* Zones = context, not alerts */
        zone: {
          eez: "hsl(0 0% 20%)",
          restricted: "hsl(0 0% 15%)",
          port: "hsl(0 0% 25%)",
          shipping: "hsl(0 0% 30%)",
        },
      },

      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },

      /* ==================================================
         MOTION — QUIET & PROFESSIONAL
         ================================================== */
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-left": {
          "0%": { transform: "translateX(-100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },

      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.25s ease-out",
        "slide-in-left": "slide-in-left 0.25s ease-out",
      },

      /* ==================================================
         DEPTH — NO GLOW, NO FUTURISM
         ================================================== */
      backgroundImage: {
        "gradient-card":
          "linear-gradient(180deg, hsl(0 0% 12%), hsl(0 0% 8%))",
      },
      boxShadow: {
        card: "0 6px 20px hsl(0 0% 0% / 0.6)",
        elevated: "0 10px 30px hsl(0 0% 0% / 0.8)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;

