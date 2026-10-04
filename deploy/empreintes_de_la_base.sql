-- Empreintes de la base, à comparer avant et après une migration.
--
--   docker compose exec -T db psql -U justi -d <base> -X -q -f - < deploy/empreintes_de_la_base.sql > avant.txt
--   (migrer)
--   … > apres.txt ; diff avant.txt apres.txt
--
-- Lecture seule. Les mêmes requêtes tournent sur le schéma de la 1.3 et
-- sur celui de la 2.0 : ce qu'une migration n'a pas le droit de toucher —
-- lignes, montants, enveloppes, pièces, dossiers — doit sortir identique,
-- à l'octet. Le journal d'audit et l'historique, eux, grandissent : la
-- migration y écrit ce qu'elle fait. La dernière section ne tourne que sur
-- un schéma 2.0 : chaque dossier rangé dans un projet de son pays.
\pset footer off
\pset pager off

\echo '== Nombre de lignes par table (audit et historique grandissent à la migration)'
select 'lignes' as objet, count(*) from expenses_expense
union all select 'dossiers', count(*) from expenses_dossier
union all select 'pieces', count(*) from expenses_proof
union all select 'enveloppes', count(*) from budget_budget
union all select 'reallocations', count(*) from budget_budgetreallocation
union all select 'comptes', count(*) from auth_user
union all select 'pays', count(*) from core_country
union all select 'audit (grandit)', count(*) from expenses_auditlog
union all select 'historique (grandit)', count(*) from core_changelog;

\echo '== Lignes par statut : nombre, montant, montant justifié'
select status, count(*), sum(amount) as montant, sum(justified_amount) as justifie
from expenses_expense group by status order by status;

\echo '== Lignes par enveloppe et par statut'
select budget_id, status, count(*), sum(amount) as montant
from expenses_expense group by budget_id, status order by budget_id nulls first, status;

\echo '== Enveloppes : montant alloué'
select id, country_id, year, amount, is_active from budget_budget order by id;

\echo '== Empreintes (une ligne modifiée, ajoutée ou retirée change la somme)'
select 'lignes' as objet, md5(coalesce(string_agg(concat_ws('|',
    id, dossier_id, country_id, team_id, owner_id, project_id, budget_id, date, title,
    amount, justified_amount, original_currency, original_amount, original_rate, status
  ), ',' order by id), '')) from expenses_expense
union all select 'dossiers', md5(coalesce(string_agg(concat_ws('|',
    id, country_id, team_id, date, status
  ), ',' order by id), '')) from expenses_dossier
union all select 'pieces', md5(coalesce(string_agg(concat_ws('|',
    id, dossier_id, file, sha256, status
  ), ',' order by id), '')) from expenses_proof
union all select 'enveloppes', md5(coalesce(string_agg(concat_ws('|',
    id, country_id, year, project_id, team_id, amount, overrun_policy, is_active
  ), ',' order by id), '')) from budget_budget;

select exists (
  select 1 from information_schema.columns
  where table_name = 'expenses_dossier' and column_name = 'project_id'
) as schema_2_0 \gset
\if :schema_2_0
\echo '== 2.0 : chaque dossier dans un projet de son pays (attendu : 0 et 0)'
select count(*) filter (where d.project_id is null) as dossiers_sans_projet,
       count(*) filter (where p.country_id <> d.country_id) as projet_d_un_autre_pays
from expenses_dossier d left join core_project p on p.id = d.project_id;

\echo '== 2.0 : projets « Historique (avant 2.0) » et dossiers rangés dessous'
select p.country_id, p.reference, count(d.id) as dossiers
from core_project p left join expenses_dossier d on d.project_id = p.id
where p.name = 'Historique (avant 2.0)'
group by p.country_id, p.reference order by p.country_id;

\echo '== 2.0 : projets sans référence (attendu : 0)'
select count(*) as sans_reference from core_project where coalesce(reference, '') = '';
\endif
