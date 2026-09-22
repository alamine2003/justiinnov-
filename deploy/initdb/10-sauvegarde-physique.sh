#!/bin/sh
# Joué par l'image Postgres à la première initialisation du cluster
# (/docker-entrypoint-initdb.d), jamais sur un cluster existant.
#
# `pg_basebackup` — la sauvegarde physique hebdomadaire, point de départ de
# la reprise à un instant donné — ouvre une connexion de RÉPLICATION, pas
# une connexion ordinaire. Le pg_hba.conf que l'image écrit n'autorise la
# réplication que depuis la machine elle-même (127.0.0.1, ::1) : depuis le
# service `sauvegarde`, un autre conteneur du même réseau, la connexion
# était refusée — « no pg_hba.conf entry for replication connection » —,
# et la sauvegarde physique échouait chaque semaine sans qu'aucun test
# statique puisse le voir. Trouvé par la CI (travail « Pile de production »)
# la première fois qu'elle a joué la pile livrée.
#
# `samenet` : n'importe quelle adresse des réseaux auxquels la base est
# raccordée, c'est-à-dire le réseau Compose de la pile — pas l'Internet, et
# pas le réseau privé de l'hébergeur (une réplique sur une autre machine
# garde sa propre ligne, ajoutée à la main : README.md, « Réplique »). Le
# mot de passe reste exigé (scram-sha-256), et seul le rôle propriétaire
# est admis. Un cluster déjà en service reçoit la même ligne une fois, à
# la main (README.md, « Reprise à un instant donné »).
set -eu
echo "host replication ${POSTGRES_USER} samenet scram-sha-256" >> "$PGDATA/pg_hba.conf"
