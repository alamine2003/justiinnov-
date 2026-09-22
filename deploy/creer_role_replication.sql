-- Rôle de réplication : celui que la seconde machine présente pour suivre
-- la primaire. À jouer **sur la primaire**, une fois, par le propriétaire :
--
--   docker compose -f docker-compose.prod.yml exec -T db \
--     psql -v ON_ERROR_STOP=1 -v role_replication=replicateur \
--          -v mot_de_passe="'…'" -U "$POSTGRES_MIGRATION_USER" \
--          -d "$POSTGRES_DB" -f - < creer_role_replication.sql
--
-- CE QUE CE RÔLE PEUT, ET CE QU'IL NE PEUT PAS. `REPLICATION` donne le
-- droit de lire le flux des journaux — donc **toutes les données**, y
-- compris les jetons de session et les secrets TOTP. C'est le prix d'une
-- réplique, et c'est pourquoi :
--
--   1. le mot de passe est aussi sérieux que celui du propriétaire ;
--   2. `pg_hba.conf` ne l'accepte que depuis l'adresse de la seconde
--      machine, jamais depuis « tout le monde » (voir README.md) ;
--   3. le flux ne traverse pas l'Internet en clair — réseau privé, ou
--      tunnel. Un flux de réplication intercepté, c'est la base entière.
--
-- Il n'a en revanche AUCUN droit sur les tables : il ne se connecte pas à
-- la base, il lit le journal. Un `SELECT` de sa part est refusé.

\if :{?role_replication}
\else
  \set role_replication 'replicateur'
\endif

\if :{?mot_de_passe}
\else
  DO $$ BEGIN RAISE EXCEPTION 'Passez le mot de passe du rôle : -v mot_de_passe=...'; END $$;
\endif

-- Création si absent (Postgres n'a pas de CREATE ROLE IF NOT EXISTS), puis
-- mot de passe à jour dans tous les cas : rejouer ce script le renouvelle,
-- ce qu'il faut faire après toute suspicion de fuite.
SELECT format('CREATE ROLE %I WITH REPLICATION LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'role_replication')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_replication') \gexec
ALTER ROLE :"role_replication" WITH REPLICATION LOGIN PASSWORD :'mot_de_passe';

-- Pas de droit de connexion à la base : il n'en a pas besoin, et le lui
-- refuser réduit ce qu'un mot de passe volé permet de faire.
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', current_database(), :'role_replication') \gexec

\echo 'Rôle de réplication prêt. Reste à autoriser son adresse dans pg_hba.conf'
\echo '(README.md, « Réplique en attente chaude »), puis à recharger la configuration.'
