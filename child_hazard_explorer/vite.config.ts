import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // data/ holds the ETL output (catalog, hazard rollups, boundaries).
  publicDir: "data",
  base: "./",
});
