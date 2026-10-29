-- Rôle du BI de pilotage (décision 122) : Grafana lit le schéma `bi`, et
-- rien d'autre.
--
-- Les vues du schéma `bi` (backend/reporting/bi/vues.sql) appartiennent au
-- propriétaire des tables, qui les repose après chaque migration ; elles
-- lisent les tables avec ses droits. Ce rôle-ci ne reçoit que la lecture de
-- ces vues : ni les tables du schéma `public` (comptes, jetons, secrets de
-- double authentification, pièces), ni l'écriture, ni le DDL. Ses sessions
-- sont en lecture seule et ses requêtes bornées dans le temps : un tableau
-- mal écrit ne bloque pas la base de l'application.
--
-- À jouer en tant que **propriétaire** (le rôle des migrations, `justi`
-- par défaut) : ALTER DEFAULT PRIVILEGES ne vaut que pour les objets que
-- crée le rôle qui le déclare, et ce sont ses vues, recréées à chaque
-- démarrage, qui doivent rester lisibles. Idempotent, rejoué par
-- restaurer.sh après une restauration :
--
--   docker compose -f docker-compose.prod.yml exec -T db \
--       psql -U justi -d justi_innov -v ON_ERROR_STOP=1 \
--       -v role_bi=justi_bi -v mot_de_passe='…' \
--       -f - < creer_role_bi.sql
--
-- Puis, dans .env : BI_DB_PASSWORD (le même mot de passe), que Grafana lit.
-- Voir deploy/README.md, « BI de pilotage ».

\set ON_ERROR_STOP on

\if :{?role_bi}
\else
  \set role_bi justi_bi
\endif
\if :{?mot_de_passe}
\else
  DO $$ BEGIN RAISE EXCEPTION 'Passez le mot de passe du rôle : -v mot_de_passe=...'; END $$;
\endif

-- Joué par un autre rôle que le propriétaire des tables, ALTER DEFAULT
-- PRIVILEGES (plus bas) vaudrait pour ses objets à lui : les vues, que le
-- propriétaire recrée après chaque migration, ne seraient plus lisibles et
-- le BI se viderait au premier redémarrage. On refuse plutôt. Avant la
-- première migration (pas de django_migrations), rien à vérifier.
SELECT format('DO $refus$ BEGIN RAISE EXCEPTION %L; END $refus$', format(
  'Jouez ce script en tant que %s, propriétaire des tables, et non %s.',
  t.tableowner, current_user))
FROM pg_tables AS t
WHERE t.schemaname = 'public' AND t.tablename = 'django_migrations'
  AND t.tableowner <> current_user \gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION',
  :'role_bi')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_bi') \gexec
ALTER ROLE :"role_bi" WITH PASSWORD :'mot_de_passe';
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'role_bi') \gexec

-- debut des droits (rejoué tel quel par reporting/tests/test_bi.py)
-- Quatre pour Grafana (provisioning-bi/datasources/bi.yml), le reste pour
-- pgAdmin et psql ; au-delà, c'est un abus.
ALTER ROLE :"role_bi" CONNECTION LIMIT 8;
-- Lecture seule, même si un jour un droit d'écriture lui était donné par
-- erreur ; requêtes bornées ; une transaction oubliée ne tient pas de verrou.
ALTER ROLE :"role_bi" SET default_transaction_read_only = on;
ALTER ROLE :"role_bi" SET statement_timeout = '30s';
ALTER ROLE :"role_bi" SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE :"role_bi" SET search_path = bi;

-- Rien sur le schéma de l'application, même si un droit y avait été posé.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"role_bi";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"role_bi";
REVOKE CREATE ON SCHEMA public FROM :"role_bi";

-- Le schéma existe dès la première migration ; le créer ici permet de
-- jouer ce script avant, sans dépendre de l'ordre.
CREATE SCHEMA IF NOT EXISTS bi;
GRANT USAGE ON SCHEMA bi TO :"role_bi";
REVOKE CREATE ON SCHEMA bi FROM :"role_bi";
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO :"role_bi";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA bi TO :"role_bi";
-- Les vues sont recréées après chaque migration : sans ces défauts, le BI
-- perdrait la vue au premier redémarrage.
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO :"role_bi";
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT EXECUTE ON FUNCTIONS TO :"role_bi";
-- fin des droits

\echo 'Rôle' :role_bi 'prêt sur' :DBNAME ': lecture seule du schéma bi.'
