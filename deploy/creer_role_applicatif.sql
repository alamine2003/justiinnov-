-- Rôle applicatif à moindre privilège pour le service Django.
--
-- Le rôle propriétaire (POSTGRES_USER de la pile, `justi` par défaut) crée
-- les tables : c'est lui qui joue les migrations et `createcachetable`. Le
-- serveur, lui, n'a besoin que de lire et d'écrire des lignes. Avec ce rôle,
-- une injection SQL ou une dépendance compromise ne peut ni supprimer une
-- table, ni en créer, ni modifier le schéma — et surtout pas vider le
-- journal d'audit d'un `DROP TABLE`.
--
-- À jouer en tant que propriétaire, sur la base de la pile, idempotent
-- (rejouable après une restauration) :
--
--   docker compose -f docker-compose.prod.yml exec -T db \
--       psql -U justi -d justi_innov -v ON_ERROR_STOP=1 \
--       -v role_applicatif=justi_app -v mot_de_passe='…' \
--       -f - < creer_role_applicatif.sql
--
-- Puis, dans .env : POSTGRES_MIGRATION_USER=justi (et son mot de passe),
-- POSTGRES_USER=justi_app (et le sien). Voir README.md.

\set ON_ERROR_STOP on

-- Valeurs par défaut des variables psql, si l'appelant ne les fournit pas.
\if :{?role_applicatif}
\else
  \set role_applicatif justi_app
\endif
\if :{?mot_de_passe}
\else
  -- Une exception plutôt qu'un \echo : avec ON_ERROR_STOP, psql sort en
  -- erreur (code 3) et le script appelant s'arrête.
  DO $$ BEGIN RAISE EXCEPTION 'Passez le mot de passe du rôle : -v mot_de_passe=...'; END $$;
\endif

-- Création si absent (Postgres n'a pas de CREATE ROLE IF NOT EXISTS), puis
-- mot de passe à jour dans tous les cas : rejouer le script le renouvelle.
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'role_applicatif')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_applicatif') \gexec
ALTER ROLE :"role_applicatif" WITH PASSWORD :'mot_de_passe';

-- Connexion à cette base, usage du schéma — et rien d'autre sur le schéma :
-- pas de CREATE, donc pas de nouvelle table, vue ni fonction.
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'role_applicatif') \gexec
GRANT USAGE ON SCHEMA public TO :"role_applicatif";
REVOKE CREATE ON SCHEMA public FROM :"role_applicatif";
-- Avant Postgres 15, PUBLIC avait CREATE sur le schéma public : on le retire
-- pour que le rôle ne l'hérite pas par ce biais. Le propriétaire garde tout.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Lignes : lecture et écriture sur les tables existantes…
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"role_applicatif";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"role_applicatif";

-- … et sur celles que le propriétaire (le rôle qui joue ce script, donc les
-- migrations à venir) créera plus tard. Sans cela, chaque migration qui
-- ajoute une table laisserait le service sans accès à celle-ci.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"role_applicatif";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"role_applicatif";

-- Pas de TRUNCATE : ni Django ni l'application n'en émettent, et c'est la
-- seule façon de vider une table d'un coup sans passer par DELETE ligne à
-- ligne (journalisé par les signaux de `core`).

\echo 'Rôle' :role_applicatif 'prêt sur' :DBNAME ': lecture-écriture des lignes, sans DDL.'
