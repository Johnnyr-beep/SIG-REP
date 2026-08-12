# syntax=docker/dockerfile:1.7
#
# Imagen del frontend de SIGREP: compila la SPA con Node y la sirve con Nginx.
# La imagen final no lleva Node ni node_modules — solo estáticos y el servidor.

# ── Compilación ───────────────────────────────────────────────────────────────
FROM node:22-alpine AS compilacion

WORKDIR /build

# Copiar solo los manifiestos primero aprovecha la caché de capas: cambiar el
# código de la aplicación no obliga a reinstalar node_modules.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src

# `npm run build` es `tsc -b && vite build`: si los tipos no cuadran, la imagen
# no se construye. Es la misma verificación que hace el CI, repetida donde de
# verdad importa.
#
# `VITE_SIGREP_EJEMPLOS` se deja deliberadamente sin definir: la interfaz
# consulta el backend real. Nunca construya una imagen con el modo de datos de
# ejemplo activo — pintaría cifras ficticias con aspecto de reporte gerencial.
RUN npm run build

# ── Servido ───────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS produccion

COPY --from=compilacion /build/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
# nginx carga `conf.d/*.conf` en el contexto `http`, y este fragmento solo
# contiene `add_header`, que ahí no es válido. La extensión `.inc` lo mantiene
# fuera de ese comodín y disponible para los `include` explícitos.
COPY docker/cabeceras-seguridad.conf /etc/nginx/conf.d/cabeceras-seguridad.inc

# Nginx necesita escribir en estos directorios para correr sin root.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
