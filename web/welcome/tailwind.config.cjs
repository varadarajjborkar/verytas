// The landing page (public/welcome) is plain HTML, so its Tailwind classes are compiled once into a static
// stylesheet instead of loading Tailwind in the browser. Rebuild after editing the pages: pnpm welcome:css
module.exports = {
    darkMode: "class",
    theme: {
      extend: {
        fontFamily: { sans: ["Geist", "ui-sans-serif", "system-ui"], mono: ["Geist Mono", "ui-monospace"] },
        colors: {
          accent: { DEFAULT: "#1a5fd1", dark: "#4c9bff" },
          ink: { 0: "#0c0e13", 1: "#13161d", 2: "#1a1e27", 3: "#232835", 4: "#313847" },
          line: "#d9dde4", raised: "#fbfbfc", surface: "#f6f7f9",
        },
        transitionTimingFunction: { out: "cubic-bezier(0.22, 1, 0.36, 1)" },
      },
    },
  };
module.exports.content = ["./public/welcome/*.html"];
