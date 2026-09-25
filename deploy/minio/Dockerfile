# MinIO et son client `mc`, construits depuis leurs sources (décision 94).
#
# MinIO ne publie plus d'images : `quay.io/minio/minio` refuse le
# téléchargement anonyme et `minio/minio` a disparu de Docker Hub — le
# 25 septembre 2026, la CI et la livraison (`compose pull`) s'arrêtaient
# net. Cette image reprend **les mêmes versions** que les images officielles
# qui tournaient en production, pour ne rien changer au format des données
# du volume `miniodata` :
#
#   minio  RELEASE.2025-04-22T22-12-26Z  (commit 0d7408fc9969)
#   mc     RELEASE.2025-04-16T18-13-26Z  (commit b00526b153a3)
#
# Les sources viennent du proxy de modules Go, vérifiées contre la base de
# sommes publique (sum.golang.org) : un octet modifié en route fait échouer
# la construction. Les pseudo-versions ci-dessous désignent le commit exact
# de chaque étiquette de publication.
#
# Un seul binaire par outil, un même conteneur pour les deux usages :
# `minio server` (service `minio`, dont le contrôle de santé appelle
# `mc ready local`) et `sauvegarder.sh pieces` (service `sauvegarde-pieces`,
# qui appelle `mc mirror` dans un shell POSIX — celui de BusyBox, comme dans
# l'image postgres qui exécute déjà le même script).
#
# L'étiquette de l'image finit par les douze premiers caractères de
# l'empreinte de ce fichier (`sha256sum deploy/minio/Dockerfile`). Changer
# une version, la chaîne Go ou même un commentaire, c'est donc changer
# l'étiquette dans docker-compose.yml et deploy/docker-compose.prod.yml : la
# CI le vérifie (`ci.yml`, « Images Docker »), et la livraison ne republie
# jamais une étiquette existante (`cd.yml`).

# Go 1.25 : la chaîne 1.24 n'est plus maintenue ; MinIO exige 1.24 ou plus.
FROM golang:1.27.1-alpine3.24 AS construction

ARG MINIO_MODULE=github.com/minio/minio@v0.0.0-20250422221226-0d7408fc9969
ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
ARG MINIO_DATE=2025-04-22T22:12:26Z
ARG MINIO_COMMIT=0d7408fc9969
ARG MC_MODULE=github.com/minio/mc@v0.0.0-20250416181326-b00526b153a3
ARG MC_RELEASE=RELEASE.2025-04-16T18-13-26Z
ARG MC_DATE=2025-04-16T18:13:26Z
ARG MC_COMMIT=b00526b153a3

# Binaires statiques, sans chemin de la machine de construction ; la chaîne
# Go est celle de l'image, jamais une autre téléchargée en cours de route.
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOBIN=/sortie

# Les variables de version sont celles qu'écrit le Makefile de MinIO :
# sans elles, `minio --version` dit « DEVELOPMENT.GOGET ».
RUN go install -trimpath -ldflags "-s -w \
      -X github.com/minio/minio/cmd.Version=${MINIO_DATE} \
      -X github.com/minio/minio/cmd.ReleaseTag=${MINIO_RELEASE} \
      -X github.com/minio/minio/cmd.CommitID=${MINIO_COMMIT} \
      -X github.com/minio/minio/cmd.ShortCommitID=${MINIO_COMMIT}" \
      "${MINIO_MODULE}" \
 && go install -trimpath -ldflags "-s -w \
      -X github.com/minio/mc/cmd.Version=${MC_DATE} \
      -X github.com/minio/mc/cmd.ReleaseTag=${MC_RELEASE} \
      -X github.com/minio/mc/cmd.CommitID=${MC_COMMIT}" \
      "${MC_MODULE}" \
 && /sortie/minio --version && /sortie/mc --version

FROM alpine:3.24.2

# Certificats pour une copie `mc` vers un stockage en TLS ; rien d'autre.
RUN apk add --no-cache ca-certificates

COPY --from=construction /sortie/minio /sortie/mc /usr/bin/

# Comme l'image officielle : root, `/data` en volume, `minio` en point
# d'entrée (`command: server /data` dans Compose). Les fichiers déjà écrits
# dans `miniodata` appartiennent à root ; un autre compte ne les lirait pas.
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/minio"]
