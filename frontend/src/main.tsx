/** Punto de entrada del frontend. */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { ErrorApi } from "@/api/cliente";
import { App } from "@/App";
import { ProveedorAuth } from "@/auth/ContextoAuth";
import { ProveedorMarca } from "@/marca/ContextoMarca";

import "./estilos.css";

const clienteConsultas = new QueryClient({
  defaultOptions: {
    queries: {
      // Reintentar un 403 o un 404 no cambia el resultado y retrasa el mensaje
      // que el usuario necesita ver.
      retry: (intentos, error) => {
        if (
          error instanceof ErrorApi &&
          error.estado >= 400 &&
          error.estado < 500
        )
          return false;
        return intentos < 2;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});

const contenedor = document.getElementById("raiz");
if (!contenedor)
  throw new Error("No se encontró el nodo raíz de la aplicación.");

createRoot(contenedor).render(
  <StrictMode>
    <QueryClientProvider client={clienteConsultas}>
      <BrowserRouter>
        {/* La marca envuelve a la sesión, no al revés: la unidad de negocio se
            elige antes de que haya nadie a quien identificar, y sobrevive al
            cierre de sesión. */}
        <ProveedorMarca>
          <ProveedorAuth>
            <App />
          </ProveedorAuth>
        </ProveedorMarca>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
