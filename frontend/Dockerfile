# Étape « deps » : Node et les dépendances, sans le build.
# C'est l'image utilisée en développement, où le code est monté en volume et
# recompilé à la volée par Vite.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package*.json ./
# `npm ci` seul : il installe exactement le fichier de verrouillage et
# échoue s'il diverge de package.json. Se rabattre sur `npm install`
# masquerait cette divergence et construirait une image avec d'autres
# versions que celles testées.
RUN npm ci

# Étape « build » : compilation des fichiers statiques.
FROM deps AS build
COPY . .
RUN npm run build

# Étape finale : service des fichiers par nginx, en production.
FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
# Le processus maître reste root : il lui faut lier le port 80 et ouvrir les
# journaux, puis il abandonne ses privilèges — les workers, qui traitent les
# requêtes, tournent sous `nginx` (directive `user` de l'image). Passer en
# `USER nginx` imposerait un port haut et des chemins réécrits pour un gain
# nul : le maître ne lit jamais une requête.
CMD ["nginx", "-g", "daemon off;"]
