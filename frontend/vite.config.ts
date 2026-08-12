import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5174,
    // El backend se consume por proxy en desarrollo: el navegador ve un único
    // origen y no hay que relajar CORS mientras se programa. El puerto es 5174
    // para poder tener GSC ONE (5173) y SIGREP levantados a la vez.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    // Los mapas se generan en desarrollo, nunca en el paquete que se publica: la
    // imagen de producción los serviría junto al `dist` y con ellos el código
    // fuente original —693 kB solo el de dependencias—. Para depurar una
    // compilación de producción en local: `vite build --sourcemap`.
    sourcemap: process.env.NODE_ENV !== "production",
    rollupOptions: {
      output: {
        // Separar dependencias de código propio mejora el cacheo: una corrección
        // de negocio no invalida el paquete de React en el navegador.
        manualChunks: {
          proveedores: ["react", "react-dom", "react-router-dom"],
          datos: ["@tanstack/react-query"],
        },
      },
    },
  },
});
