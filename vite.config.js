import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" keeps asset + data.json paths relative, so the build works on
// GitHub Pages project sites, Netlify, Vercel, or a plain file server alike.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
