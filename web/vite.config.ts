/// <reference types="vitest" />
import path from "node:path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";

/*
  Development: the SPA on 127.0.0.1:8080, and /bff handed to the BFF on 127.0.0.1:8090
  (uvicorn bff.app.main:app --port 8090). Loopback only, both of them: the development
  identity works only for connections from this machine.

  Production: `npm run build` writes dist/, which the BFF serves itself (one origin, one
  process, the security headers of section 6.6). Nothing is loaded from anywhere else:
  the font is bundled, and there are no analytics or third-party scripts.
*/
const bff = process.env.ADMIN_BFF_URL ?? "http://127.0.0.1:8090";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    host: "127.0.0.1",
    port: 8080,
    strictPort: true,
    proxy: { "/bff": { target: bff, changeOrigin: false } },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: { "/bff": { target: bff, changeOrigin: false } },
  },
  build: {
    target: "es2022",
    sourcemap: false,
    // Everything inline-free: the BFF's Content-Security-Policy allows scripts from 'self' only.
    modulePreload: { polyfill: false },
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
