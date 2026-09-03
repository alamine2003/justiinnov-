# Étape « deps » : Node et les dépendances, sans le build.
# C'est l'image utilisée en développement, où le code est monté en volume et
# recompilé à la volée par Vite.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install

# Étape « build » : compilation des fichiers statiques.
FROM deps AS build
COPY . .
RUN npm run build

# Étape finale : service des fichiers par nginx, en production.
FROM nginx:alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
