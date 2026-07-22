import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "on-tertiary-fixed-variant": "#3c475a",
        "primary": "#adc6ff",
        "on-primary": "#002e6a",
        "surface-tint": "#adc6ff",
        "error": "#ffb4ab",
        "primary-fixed": "#d8e2ff",
        "on-error-container": "#ffdad6",
        "surface-container-low": "#0d1c2d",
        "surface-container-highest": "#273647",
        "surface-container-lowest": "#010f1f",
        "on-secondary-container": "#adb4ce",
        "secondary-container": "#3f465c",
        "surface-container-high": "#1c2b3c",
        "on-tertiary": "#263143",
        "inverse-surface": "#d4e4fa",
        "surface-bright": "#2c3a4c",
        "secondary": "#bec6e0",
        "outline-variant": "#424754",
        "background": "#051424",
        "on-tertiary-container": "#1f2a3c",
        "on-secondary-fixed-variant": "#3f465c",
        "on-secondary": "#283044",
        "surface-dim": "#051424",
        "surface": "#051424",
        "secondary-fixed-dim": "#bec6e0",
        "inverse-on-surface": "#233143",
        "outline": "#8c909f",
        "on-surface-variant": "#c2c6d6",
        "tertiary-fixed": "#d8e3fb",
        "on-primary-container": "#00285d",
        "surface-container": "#122131",
        "on-primary-fixed": "#001a42",
        "on-error": "#690005",
        "on-primary-fixed-variant": "#004395",
        "tertiary-fixed-dim": "#bcc7de",
        "on-surface": "#d4e4fa",
        "tertiary-container": "#8691a7",
        "inverse-primary": "#005ac2",
        "tertiary": "#bcc7de",
        "error-container": "#93000a",
        "primary-container": "#4d8eff",
        "surface-variant": "#273647",
        "secondary-fixed": "#dae2fd",
        "on-tertiary-fixed": "#111c2d",
        "primary-fixed-dim": "#adc6ff",
        "on-background": "#d4e4fa",
        "on-secondary-fixed": "#131b2e"
      },
      borderRadius: {
        "DEFAULT": "0.125rem",
        "lg": "0.25rem",
        "xl": "0.5rem",
        "full": "0.75rem"
      },
      spacing: {
        "gutter": "16px",
        "stack-md": "16px",
        "stack-lg": "32px",
        "stack-sm": "8px",
        "unit": "4px",
        "container-padding": "24px"
      },
      fontFamily: {
        "body-sm": ["Inter"],
        "label-caps": ["Inter"],
        "body-md": ["Inter"],
        "headline-sm": ["Inter"],
        "headline-md": ["Inter"],
        "code-sm": ["JetBrains Mono"],
        "headline-lg": ["Inter"],
        "code-md": ["JetBrains Mono"]
      },
      fontSize: {
        "body-sm": ["12px", { lineHeight: "18px", fontWeight: "400" }],
        "label-caps": ["11px", { lineHeight: "16px", letterSpacing: "0.05em", fontWeight: "700" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "headline-sm": ["18px", { lineHeight: "24px", fontWeight: "600" }],
        "headline-md": ["24px", { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "code-sm": ["11px", { lineHeight: "16px", fontWeight: "500" }],
        "headline-lg": ["30px", { lineHeight: "38px", letterSpacing: "-0.02em", fontWeight: "700" }],
        "code-md": ["13px", { lineHeight: "20px", fontWeight: "400" }]
      }
    }
  },
  plugins: [],
};
export default config;
